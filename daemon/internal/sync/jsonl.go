package sync

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/tandas/daemon/internal/db"
)

// Syncer manages synchronization between JSONL and SQLite
type Syncer struct {
	store     *db.Store
	jsonlPath string
	lastSync  time.Time
}

// New creates a new syncer
func New(store *db.Store, jsonlPath string) *Syncer {
	return &Syncer{
		store:     store,
		jsonlPath: jsonlPath,
	}
}

// ImportFromJSONL reads the JSONL file and imports into SQLite
func (s *Syncer) ImportFromJSONL() error {
	file, err := os.Open(s.jsonlPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // No file to import
		}
		return fmt.Errorf("failed to open JSONL: %w", err)
	}
	defer file.Close()

	// Clear existing data
	if err := s.store.ClearAll(); err != nil {
		return fmt.Errorf("failed to clear database: %w", err)
	}

	scanner := bufio.NewScanner(file)
	// Increase buffer size for large lines
	buf := make([]byte, 0, 64*1024)
	scanner.Buffer(buf, 1024*1024)

	lineNum := 0
	for scanner.Scan() {
		lineNum++
		line := scanner.Text()
		if line == "" {
			continue
		}

		var tanda db.Tanda
		if err := json.Unmarshal([]byte(line), &tanda); err != nil {
			fmt.Printf("Warning: failed to parse line %d: %v\n", lineNum, err)
			continue
		}

		// Initialize empty slices if nil
		if tanda.Covers == nil {
			tanda.Covers = []string{}
		}
		if tanda.DependsOn == nil {
			tanda.DependsOn = []string{}
		}
		if tanda.Notes == nil {
			tanda.Notes = []db.Note{}
		}
		if tanda.RunHistory == nil {
			tanda.RunHistory = []db.RunResult{}
		}

		if err := s.store.UpsertTanda(&tanda); err != nil {
			fmt.Printf("Warning: failed to upsert tanda %s: %v\n", tanda.ID, err)
			continue
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("error reading JSONL: %w", err)
	}

	s.lastSync = time.Now()
	return nil
}

// ExportToJSONL writes all tandas from SQLite to JSONL
func (s *Syncer) ExportToJSONL() error {
	tandas, err := s.store.GetAllTandas()
	if err != nil {
		return fmt.Errorf("failed to get tandas: %w", err)
	}

	// Create temp file first
	dir := filepath.Dir(s.jsonlPath)
	tmpFile, err := os.CreateTemp(dir, "issues-*.jsonl.tmp")
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}
	tmpPath := tmpFile.Name()

	writer := bufio.NewWriter(tmpFile)
	for _, t := range tandas {
		data, err := json.Marshal(t)
		if err != nil {
			tmpFile.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("failed to marshal tanda %s: %w", t.ID, err)
		}

		if _, err := writer.Write(data); err != nil {
			tmpFile.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("failed to write tanda %s: %w", t.ID, err)
		}
		if _, err := writer.WriteString("\n"); err != nil {
			tmpFile.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("failed to write newline: %w", err)
		}
	}

	if err := writer.Flush(); err != nil {
		tmpFile.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("failed to flush: %w", err)
	}

	if err := tmpFile.Close(); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("failed to close temp file: %w", err)
	}

	// Atomic rename
	if err := os.Rename(tmpPath, s.jsonlPath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("failed to rename: %w", err)
	}

	s.lastSync = time.Now()
	return nil
}

// LastSyncTime returns the time of the last sync
func (s *Syncer) LastSyncTime() time.Time {
	return s.lastSync
}

// NeedsSync checks if JSONL file has been modified since last sync
func (s *Syncer) NeedsSync() (bool, error) {
	info, err := os.Stat(s.jsonlPath)
	if err != nil {
		if os.IsNotExist(err) {
			return false, nil
		}
		return false, err
	}

	return info.ModTime().After(s.lastSync), nil
}
