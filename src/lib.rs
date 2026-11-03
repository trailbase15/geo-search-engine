//! Geo Search Core — Nanosecond geospatial search with H3 + R-tree
//! Auto cookie/session management included

use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::RwLock;
use h3o::{CellIndex, Resolution};
use rstar::{RTree, RTreeObject, AABB, PointDistance};

/// Global engine instance (single init, zero-copy reads)
static ENGINE: Lazy<RwLock<Option<GeoEngine>>> = Lazy::new(|| RwLock::new(None));

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub h3_resolution: u8,
    pub max_results: usize,
    pub cookie_ttl_secs: u64,
    pub bind_address: String,
    pub port: u16,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            h3_resolution: 9,
            max_results: 50,
            cookie_ttl_secs: 86400,
            bind_address: "127.0.0.1".into(),
            port: 8080,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeoRecord {
    pub id: String,
    pub lat: f64,
    pub lng: f64,
    pub name: String,
    pub category: String,
    pub metadata: HashMap<String, serde_json::Value>,
    pub h3_cell: u64,
    #[serde(skip)]
    point: [f64; 2],
}

impl GeoRecord {
    pub fn new(id: String, lat: f64, lng: f64, name: String, category: String) -> Self {
        let cell = CellIndex::from_coords((lat, lng), Resolution::try_from(9).unwrap());
        Self {
            id, lat, lng, name, category,
            metadata: HashMap::new(),
            h3_cell: cell.into(),
            point: [lng, lat],
        }
    }
}

impl RTreeObject for GeoRecord {
    type Envelope = AABB<[f64; 2]>;
    fn envelope(&self) -> Self::Envelope { AABB::from_point(self.point) }
}

impl PointDistance for GeoRecord {
    fn distance_2(&self, point: &[f64; 2]) -> f64 {
        let dx = self.point[0] - point[0];
        let dy = self.point[1] - point[1];
        dx * dx + dy * dy
    }
}

pub struct GeoEngine {
    config: Config,
    rtree: RTree<GeoRecord>,
    by_h3: HashMap<u64, Vec<String>>,
    by_id: HashMap<String, GeoRecord>,
    cookie_jar: CookieJar,
}

impl GeoEngine {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            rtree: RTree::new(),
            by_h3: HashMap::new(),
            by_id: HashMap::new(),
            cookie_jar: CookieJar::new(config.cookie_ttl_secs),
        }
    }

    pub fn bulk_load(&mut self, records: Vec<GeoRecord>) {
        for r in records {
            self.by_h3.entry(r.h3_cell).or_default().push(r.id.clone());
            self.by_id.insert(r.id.clone(), r.clone());
        }
        self.rtree = RTree::bulk_load(self.by_id.values().cloned().collect());
    }

    pub fn search_radius(&self, lat: f64, lng: f64, radius_m: f32) -> Vec<&GeoRecord> {
        let point = [lng, lat];
        self.rtree.locate_within_distance(point, radius_m as f64).collect()
    }

    pub fn search_knn(&self, lat: f64, lng: f64, k: usize) -> Vec<&GeoRecord> {
        let point = [lng, lat];
        self.rtree.nearest_neighbors(&point).take(k).collect()
    }

    pub fn search_cell(&self, lat: f64, lng: f64) -> Vec<&GeoRecord> {
        let cell = CellIndex::from_coords((lat, lng), Resolution::try_from(self.config.h3_resolution).unwrap());
        self.by_h3.get(&cell.into())
            .map(|ids| ids.iter().filter_map(|id| self.by_id.get(id)).collect())
            .unwrap_or_default()
    }

    pub fn search_category(&self, lat: f64, lng: f64, radius_m: f32, category: &str) -> Vec<&GeoRecord> {
        self.search_radius(lat, lng, radius_m)
            .into_iter()
            .filter(|r| r.category == category)
            .collect()
    }

    pub fn cookie_jar(&mut self) -> &mut CookieJar { &mut self.cookie_jar }
}

pub struct CookieJar {
    store: HashMap<String, CookieEntry>,
    ttl_secs: u64,
}

#[derive(Debug, Clone)]
struct CookieEntry {
    value: String,
    domain: String,
    path: String,
    expires: u64,
    secure: bool,
    http_only: bool,
}

impl CookieJar {
    fn new(ttl_secs: u64) -> Self {
        Self { store: HashMap::new(), ttl_secs }
    }

    pub fn set(&mut self, name: String, value: String, domain: String, path: String, secure: bool, http_only: bool) {
        let expires = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH).unwrap()
            .as_secs() + self.ttl_secs;
        self.store.insert(name, CookieEntry { value, domain, path, expires, secure, http_only });
    }

    pub fn get(&self, name: &str) -> Option<&str> {
        self.store.get(name).and_then(|e| {
            let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
            if now > e.expires { None } else { Some(e.value.as_str()) }
        })
    }

    pub fn get_all_for_domain(&self, domain: &str) -> Vec<(String, String)> {
        let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        self.store.iter()
            .filter(|(_, e)| e.domain == domain && now <= e.expires)
            .map(|(k, v)| (k.clone(), v.value.clone()))
            .collect()
    }

    pub fn as_header(&self, domain: &str) -> String {
        self.get_all_for_domain(domain)
            .into_iter()
            .map(|(k, v)| format!("{}={}", k, v))
            .collect::<Vec<_>>()
            .join("; ")
    }
}

// ──────────────────────────────────────────────
// Python bindings (PyO3)
// ──────────────────────────────────────────────
#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pyclass]
struct PyGeoEngine { inner: GeoEngine }

#[cfg(feature = "python")]
#[pymethods]
impl PyGeoEngine {
    #[new]
    fn new(config: Option<PyConfig>) -> Self {
        Self { inner: GeoEngine::new(config.unwrap_or_default().into()) }
    }

    fn bulk_load(&mut self, records: Vec<PyGeoRecord>) {
        self.inner.bulk_load(records.into_iter().map(|r| r.into()).collect());
    }

    fn search_radius(&self, lat: f64, lng: f64, radius_m: f32) -> Vec<PyGeoRecord> {
        self.inner.search_radius(lat, lng, radius_m).into_iter().cloned().map(|r| r.into()).collect()
    }

    fn search_knn(&self, lat: f64, lng: f64, k: usize) -> Vec<PyGeoRecord> {
        self.inner.search_knn(lat, lng, k).into_iter().cloned().map(|r| r.into()).collect()
    }

    fn search_category(&self, lat: f64, lng: f64, radius_m: f32, category: String) -> Vec<PyGeoRecord> {
        self.inner.search_category(lat, lng, radius_m, &category).into_iter().cloned().map(|r| r.into()).collect()
    }

    fn set_cookie(&mut self, name: String, value: String, domain: String, path: String, secure: bool, http_only: bool) {
        self.inner.cookie_jar().set(name, value, domain, path, secure, http_only);
    }

    fn get_cookie(&self, name: String) -> Option<String> {
        self.inner.cookie_jar().get(&name).map(|s| s.to_string())
    }

    fn get_cookie_header(&self, domain: String) -> String {
        self.inner.cookie_jar().as_header(&domain)
    }
}

#[cfg(feature = "python")]
#[pyclass]
#[derive(Clone)]
struct PyGeoRecord {
    #[pyo3(get, set)] id: String,
    #[pyo3(get, set)] lat: f64,
    #[pyo3(get, set)] lng: f64,
    #[pyo3(get, set)] name: String,
    #[pyo3(get, set)] category: String,
    #[pyo3(get, set)] metadata: HashMap<String, serde_json::Value>,
}

#[cfg(feature = "python")]
impl From<GeoRecord> for PyGeoRecord {
    fn from(r: GeoRecord) -> Self {
        Self { id: r.id, lat: r.lat, lng: r.lng, name: r.name, category: r.category, metadata: r.metadata }
    }
}

#[cfg(feature = "python")]
impl From<PyGeoRecord> for GeoRecord {
    fn from(r: PyGeoRecord) -> Self {
        GeoRecord::new(r.id, r.lat, r.lng, r.name, r.category)
    }
}

#[cfg(feature = "python")]
#[pyclass]
#[derive(Clone, Default)]
struct PyConfig {
    #[pyo3(get, set)] h3_resolution: u8,
    #[pyo3(get, set)] max_results: usize,
    #[pyo3(get, set)] cookie_ttl_secs: u64,
    #[pyo3(get, set)] bind_address: String,
    #[pyo3(get, set)] port: u16,
}

#[cfg(feature = "python")]
impl From<PyConfig> for Config {
    fn from(c: PyConfig) -> Self {
        Config { h3_resolution: c.h3_resolution, max_results: c.max_results, cookie_ttl_secs: c.cookie_ttl_secs, bind_address: c.bind_address, port: c.port }
    }
}

#[cfg(feature = "python")]
impl Default for PyConfig {
    fn default() -> Self { Self { h3_resolution: 9, max_results: 50, cookie_ttl_secs: 86400, bind_address: "127.0.0.1".into(), port: 8080 } }
}

#[cfg(feature = "python")]
#[pymodule]
fn geo_search_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyGeoEngine>()?;
    m.add_class::<PyGeoRecord>()?;
    m.add_class::<PyConfig>()?;
    Ok(())
}