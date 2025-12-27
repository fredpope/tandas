package sync_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/tandas/daemon/internal/db"
	syncpkg "github.com/tandas/daemon/internal/sync"
)

func TestImportFromJSONL(t *testing.T) {
	store := newStore(t)
	jsonl := filepath.Join(t.TempDir(), "issues.jsonl")
	entry := map[string]string{
		"id":         "td-1",
		"title":      "Login",
		"status":     "active",
		"created_at": time.Now().Format(time.RFC3339),
		"updated_at": time.Now().Format(time.RFC3339),
	}
	data, _ := json.Marshal(entry)
	if err := os.WriteFile(jsonl, append(data, '\n'), 0o644); err != nil {
		t.Fatalf("write jsonl: %v", err)
	}

	syncer := syncpkg.New(store, jsonl)
	if err := syncer.ImportFromJSONL(); err != nil {
		t.Fatalf("import: %v", err)
	}

	tandas, err := store.GetAllTandas()
	if err != nil {
		t.Fatalf("get all: %v", err)
	}
	if len(tandas) != 1 {
		t.Fatalf("expected 1 tanda, got %d", len(tandas))
	}
}

func TestExportToJSONL(t *testing.T) {
	store := newStore(t)
	tanda := &db.Tanda{
		ID:        "td-2",
		Title:     "Checkout",
		Status:    "active",
		CreatedAt: time.Now().Format(time.RFC3339),
		UpdatedAt: time.Now().Format(time.RFC3339),
	}
	if err := store.UpsertTanda(tanda); err != nil {
		t.Fatalf("upsert: %v", err)
	}

	jsonl := filepath.Join(t.TempDir(), "issues.jsonl")
	syncer := syncpkg.New(store, jsonl)
	if err := syncer.ExportToJSONL(); err != nil {
		t.Fatalf("export: %v", err)
	}

	info, err := os.Stat(jsonl)
	if err != nil {
		t.Fatalf("stat exported file: %v", err)
	}
	if info.Size() == 0 {
		t.Fatalf("expected non-empty JSONL file")
	}
}

func newStore(t *testing.T) *db.Store {
	t.Helper()
	store, err := db.Open(filepath.Join(t.TempDir(), "db.sqlite"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}
