package health

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestCheckPassesAfterTransientFailures(t *testing.T) {
	var attempts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		if attempts.Add(1) < 3 {
			w.WriteHeader(http.StatusBadGateway)
			return
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	checker := &Checker{Interval: time.Millisecond, Timeout: time.Second}
	result := checker.Check(t.Context(), server.URL)

	if !result.Passed || result.StatusCode != http.StatusOK {
		t.Errorf("result = %+v; want pass with 200", result)
	}
	if result.Attempts != 3 {
		t.Errorf("attempts = %d; want 3", result.Attempts)
	}
}

func TestCheckFailsAfterRetriesExhausted(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	defer server.Close()

	checker := &Checker{Interval: time.Millisecond, Timeout: time.Second, Retries: 3}
	result := checker.Check(t.Context(), server.URL)

	if result.Passed {
		t.Errorf("result = %+v; want failure", result)
	}
	if result.StatusCode != http.StatusBadGateway {
		t.Errorf("status = %d; want 502", result.StatusCode)
	}
	if result.Error == "" || !strings.Contains(result.Error, "got status 502, want 200") {
		t.Errorf("error = %q; want the status mismatch explanation", result.Error)
	}
	if result.Attempts != 3 {
		t.Errorf("attempts = %d; want 3", result.Attempts)
	}
}

func TestCheckReportsConnectionRefusal(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	url := server.URL
	server.Close() // nothing listens there anymore

	checker := &Checker{Interval: time.Millisecond, Timeout: time.Second, Retries: 1}
	result := checker.Check(t.Context(), url)

	if result.Passed {
		t.Errorf("result = %+v; want failure", result)
	}
	if result.Error == "" {
		t.Errorf("connection refusal must surface an error")
	}
}

func TestCheckHonoursCustomExpectedStatus(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	checker := &Checker{Interval: time.Millisecond, ExpectedStatus: http.StatusNoContent}
	result := checker.Check(t.Context(), server.URL)
	if !result.Passed || result.StatusCode != http.StatusNoContent {
		t.Errorf("result = %+v; want pass with 204", result)
	}
}
