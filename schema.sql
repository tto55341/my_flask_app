DROP TABLE IF EXISTS experiments;

CREATE TABLE experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name TEXT NOT NULL,
    sample_name TEXT NOT NULL,
    experiment_date DATE NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);