//go:build linux

package system

import (
	"os"
	"strconv"
	"strings"
	"syscall"
	"time"
)

func osHostname() (string, error) { return os.Hostname() }

// ReadMetrics samples CPU, memory, and disk utilization from /proc and statfs.
func ReadMetrics() Metrics {
	memoryPercent := readMemoryPercent()
	diskPercent := readRootDiskPercent()
	cpuPercent := readCPUPercent()
	return Metrics{
		CPUPercent:    cpuPercent,
		MemoryPercent: memoryPercent,
		DiskPercent:   diskPercent,
	}
}

func readMemoryPercent() *float64 {
	raw, err := os.ReadFile("/proc/meminfo") //nolint:gosec // fixed kernel path
	if err != nil {
		return nil
	}
	total, available := -1.0, -1.0
	for _, line := range strings.Split(string(raw), "\n") {
		fields := strings.Fields(line)
		if len(fields) < 2 {
			continue
		}
		value, err := strconv.ParseFloat(fields[1], 64)
		if err != nil {
			continue
		}
		switch fields[0] {
		case "MemTotal:":
			total = value
		case "MemAvailable:":
			available = value
		}
	}
	if total <= 0 || available < 0 {
		return nil
	}
	used := (total - available) / total * 100
	return &used
}

func readRootDiskPercent() *float64 {
	var stat syscall.Statfs_t
	if err := syscall.Statfs("/", &stat); err != nil {
		return nil
	}
	total := float64(stat.Blocks) * float64(stat.Bsize)
	free := float64(stat.Bavail) * float64(stat.Bsize)
	if total <= 0 {
		return nil
	}
	used := (total - free) / total * 100
	return &used
}

// readCPUPercent takes two /proc/stat samples a short interval apart and
// returns the busy fraction of the first sample's delta.
func readCPUPercent() *float64 {
	first, ok := cpuTimes()
	if !ok {
		return nil
	}
	time.Sleep(200 * time.Millisecond)
	second, ok := cpuTimes()
	if !ok {
		return nil
	}
	totalDelta := second.total - first.total
	idleDelta := second.idle - first.idle
	if totalDelta <= 0 {
		return nil
	}
	busy := (1 - idleDelta/totalDelta) * 100
	return &busy
}

type cpuSample struct {
	total float64
	idle  float64
}

func cpuTimes() (cpuSample, bool) {
	raw, err := os.ReadFile("/proc/stat") //nolint:gosec // fixed kernel path
	if err != nil {
		return cpuSample{}, false
	}
	for _, line := range strings.Split(string(raw), "\n") {
		if !strings.HasPrefix(line, "cpu ") {
			continue
		}
		fields := strings.Fields(line)[1:]
		var total, idle float64
		for i, field := range fields {
			value, err := strconv.ParseFloat(field, 64)
			if err != nil {
				return cpuSample{}, false
			}
			total += value
			if i == 3 || i == 4 { // idle + iowait
				idle += value
			}
		}
		return cpuSample{total: total, idle: idle}, true
	}
	return cpuSample{}, false
}
