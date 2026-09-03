//go:build !linux

package system

import "os"

func osHostname() (string, error) { return os.Hostname() }

// ReadMetrics is a stub on non-Linux platforms (development hosts); the agent
// still heartbeats, it just omits utilization numbers. Real deployments run
// on Linux where the /proc-backed probes apply.
func ReadMetrics() Metrics {
	return Metrics{}
}
