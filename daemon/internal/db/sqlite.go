package db

import (
    "database/sql"
    "encoding/json"
    "fmt"

    _ "modernc.org/sqlite"
)

// Tanda represents a test in the registry
type Tanda struct {
	ID         string      `json:"id"`
	Title      string      `json:"title"`
	Status     string      `json:"status"`
	File       string      `json:"file,omitempty"`
	Covers     []string    `json:"covers"`
	DependsOn  []string    `json:"depends_on"`
	Notes      []Note      `json:"notes"`
	RunHistory []RunResult `json:"run_history"`
	CreatedAt  string      `json:"created_at"`
	UpdatedAt  string      `json:"updated_at"`
}

// Note represents a note entry
type Note struct {
	Timestamp string `json:"ts"`
	Type      string `json:"type"`
	Text      string `json:"text"`
}

// RunResult represents a test run result
type RunResult struct {
	Timestamp string `json:"ts"`
	Result    string `json:"result"`
	Duration  string `json:"duration,omitempty"`
	Trace     string `json:"trace,omitempty"`
}

// Store manages the SQLite database
type Store struct {
	db *sql.DB
}

// Open opens or creates the SQLite database
func Open(path string) (*Store, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Enable WAL mode for better concurrency
	if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to enable WAL: %w", err)
	}

	store := &Store{db: db}
	if err := store.initSchema(); err != nil {
		db.Close()
		return nil, err
	}

	return store, nil
}

func (s *Store) initSchema() error {
	schema := `
        CREATE TABLE IF NOT EXISTS tandas (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            file TEXT,
            covers TEXT,
            depends_on TEXT,
            notes TEXT,
            run_history TEXT,
            flakiness_score REAL DEFAULT 0.0,
            last_run_at TEXT,
            last_run_result TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_status ON tandas(status);
        CREATE INDEX IF NOT EXISTS idx_file ON tandas(file);
        CREATE INDEX IF NOT EXISTS idx_flakiness ON tandas(flakiness_score);
        CREATE INDEX IF NOT EXISTS idx_last_run ON tandas(last_run_at);
    `
	_, err := s.db.Exec(schema)
	return err
}

// Close closes the database connection
func (s *Store) Close() error {
	return s.db.Close()
}

// UpsertTanda inserts or updates a tanda
func (s *Store) UpsertTanda(t *Tanda) error {
	coversJSON, _ := json.Marshal(t.Covers)
	depsJSON, _ := json.Marshal(t.DependsOn)
	notesJSON, _ := json.Marshal(t.Notes)
	runHistoryJSON, _ := json.Marshal(t.RunHistory)

	flakiness := calculateFlakiness(t.RunHistory)
	var lastRunAt, lastRunResult string
	if len(t.RunHistory) > 0 {
		last := t.RunHistory[len(t.RunHistory)-1]
		lastRunAt = last.Timestamp
		lastRunResult = last.Result
	}

	_, err := s.db.Exec(`
        INSERT INTO tandas (id, title, status, file, covers, depends_on, notes, run_history,
                           flakiness_score, last_run_at, last_run_result, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            status = excluded.status,
            file = excluded.file,
            covers = excluded.covers,
            depends_on = excluded.depends_on,
            notes = excluded.notes,
            run_history = excluded.run_history,
            flakiness_score = excluded.flakiness_score,
            last_run_at = excluded.last_run_at,
            last_run_result = excluded.last_run_result,
            updated_at = excluded.updated_at
    `, t.ID, t.Title, t.Status, t.File, string(coversJSON), string(depsJSON),
		string(notesJSON), string(runHistoryJSON), flakiness, lastRunAt, lastRunResult,
		t.CreatedAt, t.UpdatedAt)

	return err
}

// GetAllTandas returns all tandas from the database
func (s *Store) GetAllTandas() ([]*Tanda, error) {
	rows, err := s.db.Query(`
        SELECT id, title, status, file, covers, depends_on, notes, run_history, created_at, updated_at
        FROM tandas
        ORDER BY updated_at DESC
    `)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tandas []*Tanda
	for rows.Next() {
		var t Tanda
		var file sql.NullString
		var coversJSON, depsJSON, notesJSON, runHistoryJSON string

		err := rows.Scan(&t.ID, &t.Title, &t.Status, &file, &coversJSON, &depsJSON,
			&notesJSON, &runHistoryJSON, &t.CreatedAt, &t.UpdatedAt)
		if err != nil {
			return nil, err
		}

		if file.Valid {
			t.File = file.String
		}

		json.Unmarshal([]byte(coversJSON), &t.Covers)
		json.Unmarshal([]byte(depsJSON), &t.DependsOn)
		json.Unmarshal([]byte(notesJSON), &t.Notes)
		json.Unmarshal([]byte(runHistoryJSON), &t.RunHistory)

		if t.Covers == nil {
			t.Covers = []string{}
		}
		if t.DependsOn == nil {
			t.DependsOn = []string{}
		}
		if t.Notes == nil {
			t.Notes = []Note{}
		}
		if t.RunHistory == nil {
			t.RunHistory = []RunResult{}
		}

		tandas = append(tandas, &t)
	}

	return tandas, rows.Err()
}

// DeleteTanda removes a tanda from the database
func (s *Store) DeleteTanda(id string) error {
	_, err := s.db.Exec("DELETE FROM tandas WHERE id = ?", id)
	return err
}

// ClearAll removes all tandas
func (s *Store) ClearAll() error {
	_, err := s.db.Exec("DELETE FROM tandas")
	return err
}

func calculateFlakiness(history []RunResult) float64 {
	if len(history) == 0 {
		return 0
	}

	failures := 0
	window := history
	if len(history) > 10 {
		window = history[len(history)-10:]
	}
	for _, run := range window {
		if run.Result == "fail" {
			failures++
		}
	}
	return float64(failures) / float64(len(window))
}
