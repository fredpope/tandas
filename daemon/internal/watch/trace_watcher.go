package watch

import (
	"fmt"
	"path/filepath"

	"github.com/fsnotify/fsnotify"
)

// TraceWatcher monitors a directory for new trace files.
type TraceWatcher struct {
	watcher  *fsnotify.Watcher
	dir      string
	callback func(string)
	done     chan struct{}
}

// NewTraceWatcher creates a watcher for the given directory.
func NewTraceWatcher(dir string, callback func(string)) (*TraceWatcher, error) {
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("failed to create trace watcher: %w", err)
	}

	if err := watcher.Add(dir); err != nil {
		watcher.Close()
		return nil, fmt.Errorf("failed to watch %s: %w", dir, err)
	}

	return &TraceWatcher{
		watcher:  watcher,
		dir:      dir,
		callback: callback,
		done:     make(chan struct{}),
	}, nil
}

// Start begins watching for new files.
func (t *TraceWatcher) Start() {
	for {
		select {
		case event, ok := <-t.watcher.Events:
			if !ok {
				return
			}
			if event.Op&(fsnotify.Create|fsnotify.Write) != 0 {
				t.callback(event.Name)
			}
		case err, ok := <-t.watcher.Errors:
			if ok {
				fmt.Printf("Trace watcher error (%s): %v\n", filepath.Base(t.dir), err)
			}
		case <-t.done:
			return
		}
	}
}

// Stop stops watching.
func (t *TraceWatcher) Stop() {
	close(t.done)
	t.watcher.Close()
}
