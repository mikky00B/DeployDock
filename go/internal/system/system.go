// Package system collects host identity and utilization metrics for heartbeats.
package system

import "runtime"

// Info describes the machine the agent runs on, reported at registration.
type Info struct {
	Hostname string
	OS       string
	Arch     string
}

// Metrics holds utilization percentages; nil means the probe is unavailable
// on this platform and should be omitted from the heartbeat.
type Metrics struct {
	CPUPercent    *float64
	MemoryPercent *float64
	DiskPercent   *float64
}

// ReadInfo returns static host identity.
func ReadInfo() Info {
	hostname, err := osHostname()
	if err != nil {
		hostname = "unknown"
	}
	return Info{
		Hostname: hostname,
		OS:       runtime.GOOS,
		Arch:     runtime.GOARCH,
	}
}
