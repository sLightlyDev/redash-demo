-- Runs automatically on first postgres startup (docker-entrypoint-initdb.d)
-- Creates and seeds Mozilla-style telemetry tables for the Redash demo

-- clients_daily: mirrors the real Mozilla BigQuery telemetry.clients_daily schema
CREATE TABLE clients_daily (
  submission_date                                        DATE,
  client_id                                              TEXT,
  normalized_channel                                     TEXT,
  os                                                     TEXT,
  country                                                TEXT,
  default_search_engine                                  TEXT,
  profile_age_in_days                                    INTEGER,
  days_since_seen                                        INTEGER,
  active_hours_sum                                       NUMERIC,
  subsession_hours_sum                                   NUMERIC,
  crashes_detected_content_sum                           INTEGER,
  crashes_detected_plugin_sum                            INTEGER,
  crash_submit_attempt_main_sum                          INTEGER,
  scalar_parent_browser_engagement_total_uri_count_sum   INTEGER,
  search_count_all                                       INTEGER,
  search_count_urlbar                                    INTEGER,
  search_count_searchbar                                 INTEGER
);

INSERT INTO clients_daily
SELECT
  submission_date,
  md5(row_number() OVER ()::text) AS client_id,
  CASE
    WHEN rnd < 0.94  THEN 'release'
    WHEN rnd < 0.975 THEN 'beta'
    WHEN rnd < 0.99  THEN 'nightly'
    ELSE                  'esr'
  END,
  CASE
    WHEN rnd2 < 0.65 THEN 'Windows'
    WHEN rnd2 < 0.85 THEN 'Darwin'
    ELSE                  'Linux'
  END,
  CASE
    WHEN rnd3 < 0.28 THEN 'US'   WHEN rnd3 < 0.38 THEN 'DE'
    WHEN rnd3 < 0.46 THEN 'FR'   WHEN rnd3 < 0.53 THEN 'PL'
    WHEN rnd3 < 0.59 THEN 'BR'   WHEN rnd3 < 0.65 THEN 'GB'
    WHEN rnd3 < 0.70 THEN 'IN'   WHEN rnd3 < 0.75 THEN 'IT'
    WHEN rnd3 < 0.79 THEN 'RU'   WHEN rnd3 < 0.83 THEN 'ES'
    WHEN rnd3 < 0.86 THEN 'CA'   WHEN rnd3 < 0.88 THEN 'JP'
    WHEN rnd3 < 0.90 THEN 'MX'   ELSE 'Other'
  END,
  CASE
    WHEN rnd4 < 0.75 THEN 'Google'     WHEN rnd4 < 0.83 THEN 'Bing'
    WHEN rnd4 < 0.91 THEN 'DuckDuckGo' WHEN rnd4 < 0.94 THEN 'Yandex'
    WHEN rnd4 < 0.97 THEN 'Ecosia'     ELSE 'Other'
  END,
  CASE
    WHEN rnd5 < 0.10 THEN (random() * 30)::int
    WHEN rnd5 < 0.55 THEN (30 + random() * 335)::int
    ELSE                  (365 + random() * 1500)::int
  END,
  CASE
    WHEN rnd6 < 0.85 THEN (random() * 2)::int
    WHEN rnd6 < 0.95 THEN (2 + random() * 12)::int
    ELSE                  (14 + random() * 50)::int
  END,
  round(greatest(0.05, exp(random() * 1.2 - 0.4))::numeric, 4),
  round(greatest(0.05, exp(random() * 1.2 - 0.3))::numeric, 4),
  CASE WHEN random() < 0.04 THEN (1 + random() * 3)::int ELSE 0 END,
  CASE WHEN random() < 0.01 THEN (1 + random() * 2)::int ELSE 0 END,
  CASE WHEN random() < 0.03 THEN 1 ELSE 0 END,
  CASE WHEN random() < 0.05 THEN 0 ELSE (10 + random() * 400 + random() * 200)::int END,
  CASE WHEN random() < 0.30 THEN 0 ELSE (1 + (-ln(random()) * 4))::int END,
  CASE WHEN random() < 0.30 THEN 0 ELSE (random() * 5)::int END,
  CASE WHEN random() < 0.60 THEN 0 ELSE (random() * 3)::int END
FROM (
  SELECT
    d::date AS submission_date,
    random() AS rnd,  random() AS rnd2, random() AS rnd3,
    random() AS rnd4, random() AS rnd5, random() AS rnd6
  FROM generate_series('2024-01-01'::date, '2024-06-30'::date, '1 day') d
  CROSS JOIN generate_series(1, 3000)
) base;

-- normandy_enrollments: real Normandy/Nimbus experiment schema with real slug names
CREATE TABLE normandy_enrollments (
  submission_date  DATE,
  experiment_slug  TEXT,
  branch_label     TEXT,
  enrolled_count   INTEGER,
  unenrolled_count INTEGER,
  converted_count  INTEGER,
  window_start     DATE,
  window_end       DATE
);

INSERT INTO normandy_enrollments
SELECT
  d::date,
  slug,
  branch,
  (500 + random() * 2000)::int,
  (random() * 200)::int,
  (random() * 400)::int,
  d::date - 7,
  d::date
FROM
  generate_series('2024-01-01'::date, '2024-06-30'::date, '1 day') d,
  unnest(ARRAY[
    'firefox-suggest-sponsored-v2',
    'pbm-onboarding-redesign',
    'newtab-weather-widget-v1',
    'urlbar-quick-suggest-rust'
  ]) slug,
  unnest(ARRAY['control', 'treatment']) branch;
