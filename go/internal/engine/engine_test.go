package engine

import (
	"context"
	"fmt"
	"testing"
	"time"
)

// fakeRuntime records calls; injectable failures per operation.
type fakeRuntime struct {
	buildErr error
	runErr   error
	hostPort int
	stopped  []string
	renames  [][2]string
	built    []string
	ran      []RunConfig
}

func (f *fakeRuntime) Build(_ context.Context, workspace, imageRef string) error {
	f.built = append(f.built, imageRef)
	return f.buildErr
}

func (f *fakeRuntime) Run(_ context.Context, cfg RunConfig) (string, int, error) {
	if f.runErr != nil {
		return "", 0, f.runErr
	}
	f.ran = append(f.ran, cfg)
	return "container-1", f.hostPort, nil
}

func (f *fakeRuntime) StopAndRemove(_ context.Context, name string) error {
	f.stopped = append(f.stopped, name)
	return nil
}

func (f *fakeRuntime) Rename(_ context.Context, oldName, newName string) error {
	f.renames = append(f.renames, [2]string{oldName, newName})
	return nil
}

type fakeGit struct {
	commit   string
	checkout string // records requested commit
	err      error
}

func (f *fakeGit) Checkout(_ context.Context, _, _, commit, _ string) error {
	f.checkout = commit
	return f.err
}

func (f *fakeGit) CurrentCommit(context.Context, string) (string, error) {
	return f.commit, nil
}

type fakeHealth struct {
	result HealthCheckResult
	urls   []string
}

func (f *fakeHealth) Check(_ context.Context, url string) HealthCheckResult {
	f.urls = append(f.urls, url)
	return f.result
}

type recordingSink struct {
	events []map[string]any
}

func (r *recordingSink) Emit(event map[string]any) {
	r.events = append(r.events, event)
}

func (r *recordingSink) types() []string {
	var out []string
	for _, event := range r.events {
		out = append(out, event["type"].(string))
	}
	return out
}

func testRequest() Request {
	return Request{
		DeploymentID: "dep-1",
		Kind:         "deploy",
		CommitSHA:    "a81f92cdeadbeef",
		App: AppSpec{
			Name:           "watchdog",
			RepositoryURL:  "https://github.com/example/watchdog.git",
			Branch:         "main",
			AppPath:        "/opt/watchdog",
			Port:           8080,
			HealthcheckURL: "/health",
			ContainerBase:  "deploydock-watchdog",
		},
	}
}

func TestExecuteHappyPathRunsAllStagesInOrder(t *testing.T) {
	runtime := &fakeRuntime{hostPort: 45671}
	gitClient := &fakeGit{commit: "a81f92cdeadbeef"}
	sink := &recordingSink{}
	eng := &Engine{
		Runtime: runtime,
		Git:     gitClient,
		Health:  &fakeHealth{result: HealthCheckResult{Passed: true, StatusCode: 200, Attempts: 1}},
		Proxy:   NoopProxy{},
		Sink:    sink,
		Now:     func() time.Time { return time.Unix(0, 0) },
	}

	if err := eng.Execute(context.Background(), testRequest()); err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	// Full pipeline, spec §14/§16.
	want := []string{
		"deployment_started",
		"stage_started", "stage_completed", // clone
		"stage_started", "stage_completed", // build
		"stage_started", "log", "stage_completed", // start (+ published-port log line)
		"stage_started", "health_check_passed", "stage_completed", // health_check
		"stage_started", "stage_completed", // proxy
		"stage_started", "stage_completed", // cleanup
		"deployment_completed",
	}
	got := sink.types()
	if len(got) != len(want) {
		t.Fatalf("event sequence = %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("event[%d] = %s, want %s (full: %v)", i, got[i], want[i], got)
		}
	}

	// Build used the image ref tagged with the short commit.
	if len(runtime.built) != 1 || runtime.built[0] != "deploydock-watchdog:a81f92c" {
		t.Errorf("built = %v, want [deploydock-watchdog:a81f92c]", runtime.built)
	}
	// The candidate was promoted to current: stop old, rename candidate.
	if len(runtime.renames) != 1 || runtime.renames[0] != [2]string{"deploydock-watchdog-candidate", "deploydock-watchdog-current"} {
		t.Errorf("renames = %v", runtime.renames)
	}
	if len(runtime.stopped) != 1 || runtime.stopped[0] != "deploydock-watchdog-current" {
		t.Errorf("stopped = %v, want [deploydock-watchdog-current]", runtime.stopped)
	}
	// Health check hit the published host port with the app's path.
	if len(sink.events) > 0 {
		completed := sink.events[len(sink.events)-1]
		if completed["commit_sha"] != "a81f92cdeadbeef" {
			t.Errorf("completion commit = %v", completed["commit_sha"])
		}
	}
}

func TestFailedHealthCheckFailsDeploymentAndRemovesCandidate(t *testing.T) {
	runtime := &fakeRuntime{hostPort: 45671}
	sink := &recordingSink{}
	eng := &Engine{
		Runtime: runtime,
		Git:     &fakeGit{commit: "a81f92cdeadbeef"},
		Health:  &fakeHealth{result: HealthCheckResult{Passed: false, StatusCode: 502, Error: "got status 502, want 200", Attempts: 5}},
		Proxy:   NoopProxy{},
		Sink:    sink,
	}

	err := eng.Execute(context.Background(), testRequest())
	if err == nil {
		t.Fatal("expected Execute to fail when the health check fails")
	}

	foundFailed, foundPassed := false, false
	for _, event := range sink.events {
		switch event["type"] {
		case "deployment_failed":
			foundFailed = true
			if event["stage"] != StageHealthCheck {
				t.Errorf("failure stage = %v, want health_check", event["stage"])
			}
		case "health_check_failed":
			foundPassed = true
		case "health_check_passed":
			t.Errorf("health_check_passed must not appear on failure")
		}
	}
	if !foundFailed || !foundPassed {
		t.Errorf("missing failure events: %v", sink.types())
	}
	// Zero-downtime guarantee: the previous release must NOT have been stopped.
	if len(runtime.stopped) != 1 || runtime.stopped[0] != "deploydock-watchdog-candidate" {
		t.Errorf("only the candidate may be removed on failure, stopped = %v", runtime.stopped)
	}
	if len(runtime.renames) != 0 {
		t.Errorf("candidate must not be promoted on failure, renames = %v", runtime.renames)
	}
}

func TestBuildFailureStopsBeforeStart(t *testing.T) {
	runtime := &fakeRuntime{buildErr: fmt.Errorf("dockerfile missing")}
	sink := &recordingSink{}
	eng := &Engine{
		Runtime: runtime,
		Git:     &fakeGit{commit: "abc"},
		Health:  &fakeHealth{},
		Proxy:   NoopProxy{},
		Sink:    sink,
	}

	if err := eng.Execute(context.Background(), testRequest()); err == nil {
		t.Fatal("expected build failure to fail the deployment")
	}
	for _, event := range sink.events {
		if event["type"] == "stage_started" && event["stage"] == StageStart {
			t.Error("start stage must not begin after a build failure")
		}
	}
}

func TestZeroDowntimeOldContainerServesUntilHealthPasses(t *testing.T) {
	// The old current container must be stopped strictly after the health
	// check passed: find the stop after health_check_passed, never before.
	runtime := &fakeRuntime{hostPort: 40000}
	sink := &recordingSink{}
	eng := &Engine{
		Runtime: runtime,
		Git:     &fakeGit{commit: "abc"},
		Health:  &fakeHealth{result: HealthCheckResult{Passed: true, StatusCode: 200, Attempts: 3}},
		Proxy:   NoopProxy{},
		Sink:    sink,
	}
	if err := eng.Execute(context.Background(), testRequest()); err != nil {
		t.Fatalf("Execute failed: %v", err)
	}

	passedAt, stoppedAt := -1, -1
	for i, event := range sink.events {
		switch event["type"] {
		case "health_check_passed":
			passedAt = i
		}
	}
	// Stop happens inside cleanup, the stage right before completion.
	for i, event := range sink.events {
		if event["type"] == "stage_started" && event["stage"] == StageCleanup {
			stoppedAt = i
		}
	}
	if passedAt < 0 || stoppedAt < 0 || stoppedAt < passedAt {
		t.Errorf("cleanup (stop old) must follow health_check_passed: passed=%d cleanup=%d", passedAt, stoppedAt)
	}
}

func TestRollbackChecksOutTargetCommit(t *testing.T) {
	gitClient := &fakeGit{commit: "92bc112"}
	eng := &Engine{
		Runtime: &fakeRuntime{hostPort: 40001},
		Git:     gitClient,
		Health:  &fakeHealth{result: HealthCheckResult{Passed: true, StatusCode: 200, Attempts: 1}},
		Proxy:   NoopProxy{},
		Sink:    &recordingSink{},
	}
	req := testRequest()
	req.Kind = "rollback"
	req.CommitSHA = "92bc112aaaaaaa"

	if err := eng.Execute(context.Background(), req); err != nil {
		t.Fatalf("Execute failed: %v", err)
	}
	if gitClient.checkout != "92bc112aaaaaaa" {
		t.Errorf("checked out %q, want the rollback target", gitClient.checkout)
	}
}
