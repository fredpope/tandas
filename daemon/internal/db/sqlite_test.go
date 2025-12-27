package db_test

import (
	"path/filepath"
	"testing"
	"time"

	"github.com/tandas/daemon/internal/db"
)

func newStore(t *testing.T) *db.Store {
	t.Helper()
	store, err := db.Open(filepath.Join(t.TempDir(), "db.sqlite"))
	if err != nil {
		t.Fatalf("open store: %v", err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func TestUpsertAndDelete(t *testing.T) {
	store := newStore(t)

	tanda := &db.Tanda{
		ID:        "td-test",
		Title:     "Checkout",
		Status:    "active",
		CreatedAt: time.Now().Format(time.RFC3339),
		UpdatedAt: time.Now().Format(time.RFC3339),
	}

	if err := store.UpsertTanda(tanda); err != nil {
		t.Fatalf("upsert: %v", err)
	}

	tandas, err := store.GetAllTandas()
	if err != nil {
		t.Fatalf("get all: %v", err)
	}
	if len(tandas) != 1 {
		t.Fatalf("expected 1 tanda, got %d", len(tandas))
	}

	if err := store.DeleteTanda("td-test"); err != nil {
		t.Fatalf("delete: %v", err)
	}

	tandas, err = store.GetAllTandas()
	if err != nil {
		t.Fatalf("get after delete: %v", err)
	}
	if len(tandas) != 0 {
		t.Fatalf("expected 0 tandas after delete, got %d", len(tandas))
	}
}

func TestClearAll(t *testing.T) {
	store := newStore(t)

	for i := 0; i < 3; i++ {
		tanda := &db.Tanda{
			ID:        "td-test-" + string(rune('a'+i)),
			Title:     "Example",
			Status:    "active",
			CreatedAt: time.Now().Format(time.RFC3339),
			UpdatedAt: time.Now().Format(time.RFC3339),
		}
		if err := store.UpsertTanda(tanda); err != nil {
			t.Fatalf("upsert %d: %v", i, err)
		}
	}

	if err := store.ClearAll(); err != nil {
		t.Fatalf("clear all: %v", err)
	}

	tandas, err := store.GetAllTandas()
	if err != nil {
		t.Fatalf("get after clear: %v", err)
	}
	if len(tandas) != 0 {
		t.Fatalf("expected 0 tandas after clear, got %d", len(tandas))
	}
}
