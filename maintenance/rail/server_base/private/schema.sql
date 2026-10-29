CREATE TABLE IF NOT EXISTS or_meta (
  meta_key VARCHAR(64) NOT NULL PRIMARY KEY,
  meta_value TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_settings (
  setting_key VARCHAR(80) NOT NULL PRIMARY KEY,
  setting_value TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_devices (
  device_id CHAR(36) NOT NULL PRIMARY KEY,
  public_key_pem TEXT NOT NULL,
  device_label VARCHAR(120) NOT NULL DEFAULT 'OpenRoad Android',
  created_at DATETIME NOT NULL,
  last_seen_at DATETIME NULL,
  revoked_at DATETIME NULL,
  KEY idx_devices_active (revoked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_nonces (
  device_id CHAR(36) NOT NULL,
  nonce_hash CHAR(64) NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY(device_id, nonce_hash),
  KEY idx_nonces_created(created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_rate_events (
  bucket_hash CHAR(64) NOT NULL,
  event_at DATETIME NOT NULL,
  KEY idx_rate_bucket_time(bucket_hash, event_at),
  KEY idx_rate_time(event_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_stops (
  dataset_id BIGINT NOT NULL,
  stop_id VARCHAR(160) NOT NULL,
  stop_name VARCHAR(255) NOT NULL,
  stop_lat DOUBLE NOT NULL,
  stop_lon DOUBLE NOT NULL,
  PRIMARY KEY(dataset_id, stop_id),
  KEY idx_stops_box(dataset_id, stop_lat, stop_lon)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_routes (
  dataset_id BIGINT NOT NULL,
  route_id VARCHAR(160) NOT NULL,
  short_name VARCHAR(120) NOT NULL DEFAULT '',
  long_name VARCHAR(255) NOT NULL DEFAULT '',
  route_type VARCHAR(24) NOT NULL DEFAULT '',
  PRIMARY KEY(dataset_id, route_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_trips (
  dataset_id BIGINT NOT NULL,
  trip_id VARCHAR(180) NOT NULL,
  route_id VARCHAR(160) NOT NULL,
  service_id VARCHAR(180) NOT NULL,
  shape_id VARCHAR(180) NOT NULL DEFAULT '',
  headsign VARCHAR(255) NOT NULL DEFAULT '',
  direction_id VARCHAR(8) NOT NULL DEFAULT '',
  PRIMARY KEY(dataset_id, trip_id),
  KEY idx_trip_service(dataset_id, service_id),
  KEY idx_trip_route(dataset_id, route_id),
  KEY idx_trip_shape(dataset_id, shape_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_stop_times (
  dataset_id BIGINT NOT NULL,
  trip_id VARCHAR(180) NOT NULL,
  stop_id VARCHAR(160) NOT NULL,
  stop_sequence INT NOT NULL,
  arrival_sec INT NOT NULL,
  departure_sec INT NOT NULL,
  PRIMARY KEY(dataset_id, trip_id, stop_sequence),
  KEY idx_stop_depart(dataset_id, stop_id, departure_sec),
  KEY idx_stop_arrive(dataset_id, stop_id, arrival_sec),
  KEY idx_stop_depart_cover(dataset_id, stop_id, departure_sec, trip_id, stop_sequence)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_service_dates (
  dataset_id BIGINT NOT NULL,
  service_id VARCHAR(180) NOT NULL,
  service_date DATE NOT NULL,
  PRIMARY KEY(dataset_id, service_id, service_date),
  KEY idx_service_date(dataset_id, service_date, service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_shapes (
  dataset_id BIGINT NOT NULL,
  shape_id VARCHAR(180) NOT NULL,
  point_sequence INT NOT NULL,
  point_lat DOUBLE NOT NULL,
  point_lon DOUBLE NOT NULL,
  PRIMARY KEY(dataset_id, shape_id, point_sequence),
  KEY idx_shape(dataset_id, shape_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_regions (
  region_key VARCHAR(64) NOT NULL PRIMARY KEY,
  dataset_id BIGINT NOT NULL,
  label VARCHAR(120) NOT NULL DEFAULT '',
  updated_at DATETIME NOT NULL,
  last_used_at DATETIME NOT NULL,
  permanent TINYINT(1) NOT NULL DEFAULT 0,
  KEY idx_regions_used(last_used_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_prepare_queue (
  region_key VARCHAR(64) NOT NULL PRIMARY KEY,
  reason VARCHAR(64) NOT NULL DEFAULT 'destination',
  requested_at DATETIME NOT NULL,
  last_requested_at DATETIME NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NULL,
  KEY idx_prepare_requested(last_requested_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_journey_cache (
  cache_key CHAR(64) NOT NULL PRIMARY KEY,
  region_key VARCHAR(64) NOT NULL,
  dataset_id BIGINT NOT NULL,
  response_json MEDIUMTEXT NOT NULL,
  created_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  KEY idx_journey_expiry(expires_at),
  KEY idx_journey_region(region_key, dataset_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS or_service_cache (
  cache_key CHAR(64) NOT NULL PRIMARY KEY,
  region_key VARCHAR(64) NOT NULL,
  dataset_id BIGINT NOT NULL,
  response_json MEDIUMTEXT NOT NULL,
  created_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  KEY idx_service_expiry(expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
