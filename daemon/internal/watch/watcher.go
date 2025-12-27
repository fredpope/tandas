package watch

import (
	"fmt"
	"path/filepath"
	"time"

	"github.com/fsnotify/fsnotify"
)

// Watcher monitors files for changes
type Watcher struct {
	watcher   *fsnotify.Watcher
	filePath  string
	callback  func()
	done      chan struct{}
	debounce  time.Duration
}

// New creates a new file watcher
func New(filePath string, callback func()) (*Watcher, error) {
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("failed to create watcher: %w", err)
	}

	// Watch the directory containing the file
	dir := filepath.Dir(filePath)
	if err := watcher.Add(dir); err != nil {
		watcher.Close()
		return nil, fmt.Errorf("failed to watch directory: %w", err)
	}

	return &Watcher{
		watcher:  watcher,
		filePath: filePath,
		callback: callback,
		done:     make(chan struct{}),
		debounce: 500 * time.Millisecond,
	}, nil
}

// Start begins watching for file changes
func (w *Watcher) Start() {
	var timer *time.Timer
	fileName := filepath.Base(w.filePath)

	for {
		select {
		case event, ok := <-w.watcher.Events:
			if !ok {
				return
			}

			// Only care about our specific file
			if filepath.Base(event.Name) != fileName {
				continue
			}

			// Only care about writes and creates
			if event.Op&(fsnotify.Write|fsnotify.Create) == 0 {
				continue
			}

			// Debounce multiple rapid events
			if timer != nil {
				timer.Stop()
			}
			timer = time.AfterFunc(w.debounce, func() {
				w.callback()
			})

		case err, ok := <-w.watcher.Errors:
			if !ok {
				return
			}
			fmt.Printf("Watcher error: %v\n", err)

		case <-w.done:
			if timer != nil {
				timer.Stop()
			}
			return
		}
	}
}

// Stop stops the watcher
func (w *Watcher) Stop() {
	close(w.done)
	w.watcher.Close()
}

// SetDebounce sets the debounce duration
func (w *Watcher) SetDebounce(d time.Duration) {
	w.debounce = d
}
