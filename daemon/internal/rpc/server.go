package rpc

import (
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/tandas/daemon/internal/db"
	"github.com/tandas/daemon/internal/sync"
	"github.com/tandas/daemon/internal/watch"
)

const (
	socketName     = "td.sock"
	pidFileName    = "daemon.pid"
	lockFileName   = "daemon.lock"
	traceInboxName = "trace_inbox.jsonl"
)

// LockFile contains daemon metadata
type LockFile struct {
	PID       int       `json:"pid"`
	ParentPID int       `json:"parent_pid"`
	Database  string    `json:"database"`
	Version   string    `json:"version"`
	StartedAt time.Time `json:"started_at"`
}

// RPCRequest is a JSON-RPC style request
type RPCRequest struct {
	Method string          `json:"method"`
	Params json.RawMessage `json:"params,omitempty"`
	ID     int             `json:"id"`
}

// RPCResponse is a JSON-RPC style response
type RPCResponse struct {
	Result interface{} `json:"result,omitempty"`
	Error  string      `json:"error,omitempty"`
	ID     int         `json:"id"`
}

// Daemon manages the background sync process
type Daemon struct {
	dir          string
	interval     time.Duration
	db           *db.Store
	syncer       *sync.Syncer
	watcher      *watch.Watcher
	traceWatcher *watch.TraceWatcher
	listener     net.Listener
	done         chan struct{}
}

// StartDaemon starts the background daemon
func StartDaemon(dir string, intervalStr string) error {
	interval, err := time.ParseDuration(intervalStr)
	if err != nil {
		return fmt.Errorf("invalid interval: %w", err)
	}

	socketPath := filepath.Join(dir, socketName)
	pidPath := filepath.Join(dir, pidFileName)
	lockPath := filepath.Join(dir, lockFileName)
	dbPath := filepath.Join(dir, "db.sqlite")
	jsonlPath := filepath.Join(dir, "issues.jsonl")

	// Check if already running
	if _, err := os.Stat(socketPath); err == nil {
		return fmt.Errorf("daemon already running (socket exists: %s)", socketPath)
	}

	// Initialize database
	store, err := db.Open(dbPath)
	if err != nil {
		return fmt.Errorf("failed to open database: %w", err)
	}

	// Initialize syncer
	syncer := sync.New(store, jsonlPath)

	// Do initial sync
	if err := syncer.ImportFromJSONL(); err != nil {
		fmt.Printf("Warning: initial import failed: %v\n", err)
	}

	// Create Unix socket
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		store.Close()
		return fmt.Errorf("failed to create socket: %w", err)
	}

	// Write PID file
	pid := os.Getpid()
	if err := os.WriteFile(pidPath, []byte(strconv.Itoa(pid)), 0644); err != nil {
		listener.Close()
		store.Close()
		return fmt.Errorf("failed to write PID file: %w", err)
	}

	// Write lock file
	lockData := LockFile{
		PID:       pid,
		ParentPID: os.Getppid(),
		Database:  dbPath,
		Version:   "0.2.0",
		StartedAt: time.Now().UTC(),
	}
	lockBytes, _ := json.MarshalIndent(lockData, "", "  ")
	if err := os.WriteFile(lockPath, lockBytes, 0644); err != nil {
		os.Remove(pidPath)
		listener.Close()
		store.Close()
		return fmt.Errorf("failed to write lock file: %w", err)
	}

	// Initialize file watcher
	watcher, err := watch.New(jsonlPath, func() {
		syncer.ImportFromJSONL()
	})
	if err != nil {
		fmt.Printf("Warning: file watcher failed: %v\n", err)
	}

	var traceWatcher *watch.TraceWatcher
	projectRoot := filepath.Clean(filepath.Join(dir, ".."))
	traceDir := filepath.Join(projectRoot, "test-results")
	if info, err := os.Stat(traceDir); err == nil && info.IsDir() {
		traceWatcher, err = watch.NewTraceWatcher(traceDir, func(path string) {
			appendTraceInbox(filepath.Join(dir, traceInboxName), projectRoot, path)
		})
		if err != nil {
			fmt.Printf("Warning: trace watcher failed: %v\n", err)
		}
	}

	daemon := &Daemon{
		dir:          dir,
		interval:     interval,
		db:           store,
		syncer:       syncer,
		watcher:      watcher,
		traceWatcher: traceWatcher,
		listener:     listener,
		done:         make(chan struct{}),
	}

	// Handle signals
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		<-sigChan
		daemon.Shutdown()
	}()

	fmt.Printf("Tandas daemon started (PID: %d, interval: %s)\n", pid, interval)
	fmt.Printf("Socket: %s\n", socketPath)

	// Start sync loop
	go daemon.syncLoop()

	// Start watcher
	if watcher != nil {
		go watcher.Start()
	}
	if traceWatcher != nil {
		go traceWatcher.Start()
	}

	// Accept connections
	daemon.acceptConnections()

	return nil
}

func (d *Daemon) syncLoop() {
	ticker := time.NewTicker(d.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if err := d.syncer.ExportToJSONL(); err != nil {
				fmt.Printf("Sync error: %v\n", err)
			}
		case <-d.done:
			return
		}
	}
}

func (d *Daemon) acceptConnections() {
	for {
		conn, err := d.listener.Accept()
		if err != nil {
			select {
			case <-d.done:
				return
			default:
				fmt.Printf("Accept error: %v\n", err)
				continue
			}
		}
		go d.handleConnection(conn)
	}
}

func (d *Daemon) handleConnection(conn net.Conn) {
	defer conn.Close()

	decoder := json.NewDecoder(conn)
	encoder := json.NewEncoder(conn)

	for {
		var req RPCRequest
		if err := decoder.Decode(&req); err != nil {
			if err != io.EOF {
				fmt.Printf("Decode error: %v\n", err)
			}
			return
		}

		resp := d.handleRequest(&req)
		if err := encoder.Encode(resp); err != nil {
			fmt.Printf("Encode error: %v\n", err)
			return
		}
	}
}

func (d *Daemon) handleRequest(req *RPCRequest) *RPCResponse {
	switch req.Method {
	case "ping":
		return &RPCResponse{Result: "pong", ID: req.ID}

	case "sync":
		if err := d.syncer.ExportToJSONL(); err != nil {
			return &RPCResponse{Error: err.Error(), ID: req.ID}
		}
		return &RPCResponse{Result: "synced", ID: req.ID}

	case "import":
		if err := d.syncer.ImportFromJSONL(); err != nil {
			return &RPCResponse{Error: err.Error(), ID: req.ID}
		}
		return &RPCResponse{Result: "imported", ID: req.ID}

	case "status":
		status := map[string]interface{}{
			"running":  true,
			"pid":      os.Getpid(),
			"interval": d.interval.String(),
		}
		return &RPCResponse{Result: status, ID: req.ID}

	default:
		return &RPCResponse{Error: fmt.Sprintf("unknown method: %s", req.Method), ID: req.ID}
	}
}

func (d *Daemon) Shutdown() {
	fmt.Println("\nShutting down daemon...")
	close(d.done)

	if d.watcher != nil {
		d.watcher.Stop()
	}
	if d.traceWatcher != nil {
		d.traceWatcher.Stop()
	}

	d.listener.Close()
	d.db.Close()

	// Cleanup files
	os.Remove(filepath.Join(d.dir, socketName))
	os.Remove(filepath.Join(d.dir, pidFileName))
	os.Remove(filepath.Join(d.dir, lockFileName))

	fmt.Println("Daemon stopped")
	os.Exit(0)
}

// StopDaemon stops a running daemon
func StopDaemon(dir string) error {
	pidPath := filepath.Join(dir, pidFileName)
	pidBytes, err := os.ReadFile(pidPath)
	if err != nil {
		return fmt.Errorf("daemon not running (no PID file)")
	}

	pid, err := strconv.Atoi(string(pidBytes))
	if err != nil {
		return fmt.Errorf("invalid PID file")
	}

	process, err := os.FindProcess(pid)
	if err != nil {
		return fmt.Errorf("process not found: %w", err)
	}

	if err := process.Signal(syscall.SIGTERM); err != nil {
		return fmt.Errorf("failed to send signal: %w", err)
	}

	fmt.Printf("Sent SIGTERM to daemon (PID: %d)\n", pid)
	return nil
}

// DaemonStatus checks if the daemon is running
func DaemonStatus(dir string) (bool, int) {
	pidPath := filepath.Join(dir, pidFileName)
	pidBytes, err := os.ReadFile(pidPath)
	if err != nil {
		return false, 0
	}

	pid, err := strconv.Atoi(string(pidBytes))
	if err != nil {
		return false, 0
	}

	// Check if process exists
	process, err := os.FindProcess(pid)
	if err != nil {
		return false, 0
	}

	// On Unix, FindProcess always succeeds, so we need to send signal 0
	if err := process.Signal(syscall.Signal(0)); err != nil {
		return false, 0
	}

	return true, pid
}

func appendTraceInbox(inboxPath, projectRoot, filePath string) {
	rel := filePath
	if projectRoot != "" {
		if r, err := filepath.Rel(projectRoot, filePath); err == nil {
			rel = r
		}
	}

	entry := map[string]interface{}{
		"path":   rel,
		"ts":     time.Now().UTC().Format(time.RFC3339),
		"source": "watcher",
		"status": "pending",
	}

	data, err := json.Marshal(entry)
	if err != nil {
		fmt.Printf("Trace inbox marshal error: %v\n", err)
		return
	}

	f, err := os.OpenFile(inboxPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		fmt.Printf("Trace inbox write error: %v\n", err)
		return
	}
	defer f.Close()

	if _, err := f.Write(append(data, '\n')); err != nil {
		fmt.Printf("Trace inbox write error: %v\n", err)
	}
}
