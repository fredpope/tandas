package main

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/tandas/daemon/internal/rpc"
)

var (
	version   = "0.2.0"
	interval  = "5s"
	socketDir = ".tandas"
)

func main() {
	rootCmd := &cobra.Command{
		Use:     "td-daemon",
		Short:   "Tandas background daemon for JSONL/SQLite sync",
		Version: version,
	}

	startCmd := &cobra.Command{
		Use:   "start",
		Short: "Start the daemon",
		RunE: func(cmd *cobra.Command, args []string) error {
			return rpc.StartDaemon(socketDir, interval)
		},
	}
	startCmd.Flags().StringVar(&interval, "interval", "5s", "Sync interval")
	startCmd.Flags().StringVar(&socketDir, "dir", ".tandas", "Tandas directory")

	stopCmd := &cobra.Command{
		Use:   "stop",
		Short: "Stop the daemon",
		RunE: func(cmd *cobra.Command, args []string) error {
			return rpc.StopDaemon(socketDir)
		},
	}
	stopCmd.Flags().StringVar(&socketDir, "dir", ".tandas", "Tandas directory")

	statusCmd := &cobra.Command{
		Use:   "status",
		Short: "Check daemon status",
		RunE: func(cmd *cobra.Command, args []string) error {
			running, pid := rpc.DaemonStatus(socketDir)
			if running {
				fmt.Printf("Daemon running (PID: %d)\n", pid)
			} else {
				fmt.Println("Daemon not running")
			}
			return nil
		},
	}
	statusCmd.Flags().StringVar(&socketDir, "dir", ".tandas", "Tandas directory")

	rootCmd.AddCommand(startCmd, stopCmd, statusCmd)

	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}
