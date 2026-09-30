// Package health implements engine.HealthChecker for HTTP targets (spec §18).
package health

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/deploydock/deploydock/go/internal/engine"
)

// Checker probes an HTTP endpoint until it returns the expected status.
type Checker struct {
	// ExpectedStatus defaults to 200.
	ExpectedStatus int
	// Timeout bounds each attempt (spec §18 example: 5s).
	Timeout time.Duration
	// Retries is the number of attempts (spec §18 example: 5).
	Retries    int
	Interval   time.Duration
	HTTPClient *http.Client
}

func (c *Checker) settings() (int, time.Duration, int, *http.Client) {
	expected := c.ExpectedStatus
	if expected == 0 {
		expected = http.StatusOK
	}
	timeout := c.Timeout
	if timeout == 0 {
		timeout = 5 * time.Second
	}
	retries := c.Retries
	if retries <= 0 {
		retries = 5
	}
	interval := c.Interval
	if interval == 0 {
		interval = 2 * time.Second
	}
	client := c.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: timeout}
	}
	return expected, interval, retries, client
}

// Check probes url until it answers with the expected status or attempts run
// out. Never blocks longer than retries × (timeout + interval).
func (c *Checker) Check(ctx context.Context, url string) engine.HealthCheckResult {
	expected, interval, retries, client := c.settings()

	var lastErr string
	var lastStatus int
	for attempt := 1; attempt <= retries; attempt++ {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return engine.HealthCheckResult{Passed: false, Error: err.Error(), Attempts: attempt}
		}
		resp, err := client.Do(req)
		if err != nil {
			lastErr = err.Error()
		} else {
			lastStatus = resp.StatusCode
			resp.Body.Close()
			if resp.StatusCode == expected {
				return engine.HealthCheckResult{Passed: true, StatusCode: resp.StatusCode, Attempts: attempt}
			}
			lastErr = fmt.Sprintf("got status %d, want %d", resp.StatusCode, expected)
		}
		if attempt < retries {
			select {
			case <-ctx.Done():
				return engine.HealthCheckResult{Passed: false, StatusCode: lastStatus, Error: lastErr, Attempts: attempt}
			case <-time.After(interval):
			}
		}
	}
	return engine.HealthCheckResult{Passed: false, StatusCode: lastStatus, Error: lastErr, Attempts: retries}
}
