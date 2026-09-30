// Package engine executes deployments on the VPS (spec §16, §70).
//
// Every infrastructure dependency sits behind an interface (spec §59) so the
// stages are testable with fakes: ContainerRuntime, GitClient, HealthChecker,
// and ProxyManager. The engine only orchestrates stages and reports progress
// through an EventSink.
package engine

import (
	"context"
	"fmt"
	"time"
)

// Stage names, matching the spec §16 stage list.
const (
	StageClone       = "clone"
	StageBuild       = "build"
	StageStart       = "start"
	StageHealthCheck = "health_check"
	StageProxy       = "proxy"
	StageCleanup     = "cleanup"
)

// Request describes one deploy or rollback execution.
type Request struct {
	DeploymentID string
	Kind         string // "deploy" or "rollback"
	CommitSHA    string // target commit; empty means branch head
	App          AppSpec
}

// AppSpec mirrors the control-plane payload (client.AppSpec) without importing
// the client package, keeping the engine dependency-free.
type AppSpec struct {
	Name           string
	RepositoryURL  string
	Branch         string
	AppPath        string // workspace directory on the VPS
	Port           int
	HealthcheckURL string
	ContainerBase  string
	Env            map[string]string
	CPULimit       string // e.g. "1.5"; empty = unlimited
	MemoryLimit    string // e.g. "512m"; empty = unlimited
}

// EventSink receives stage/log/health progress (spec §25 events).
type EventSink interface {
	Emit(event map[string]any)
}

// sink adapts EventSink calls with the deployment id attached.
type sink struct {
	deploymentID string
	out          EventSink
}

func (s sink) emit(event map[string]any) {
	event["deployment_id"] = s.deploymentID
	s.out.Emit(event)
}

// ContainerRuntime abstracts Docker (spec §34).
type ContainerRuntime interface {
	// Build builds an image from the workspace and returns the image reference.
	Build(ctx context.Context, workspace, imageRef string) error
	// Run starts a detached container publishing its port on 127.0.0.1 with a
	// random host port, and returns the container id and the chosen host port.
	Run(ctx context.Context, cfg RunConfig) (containerID string, hostPort int, err error)
	// StopAndRemove stops and removes a container by name, ignoring absence.
	StopAndRemove(ctx context.Context, name string) error
	// Rename renames a container.
	Rename(ctx context.Context, oldName, newName string) error
}

// RunConfig is one container launch.
type RunConfig struct {
	Name        string
	Image       string
	Port        int // container port to publish; 0 = none
	Env         map[string]string
	CPULimit    string
	MemoryLimit string
	Labels      map[string]string
}

// PublishedPort is the host port a started container is reachable on.
type PublishedPort = int

// GitClient abstracts repository checkout (spec §16 CloneStage).
type GitClient interface {
	Checkout(ctx context.Context, repoURL, branch, commit, workspace string) error
	CurrentCommit(ctx context.Context, workspace string) (string, error)
}

// HealthCheckResult is the outcome of one probe series.
type HealthCheckResult struct {
	Passed     bool
	StatusCode int
	Error      string
	Attempts   int
}

// HealthChecker abstracts the health-check stage (spec §18).
type HealthChecker interface {
	Check(ctx context.Context, url string) HealthCheckResult
}

// ProxyManager abstracts nginx configuration (spec §35).
type ProxyManager interface {
	Configure(ctx context.Context, cfg ProxyConfig) error
}

// ProxyConfig is one managed reverse-proxy entry.
type ProxyConfig struct {
	AppName    string
	Port       int // upstream port on 127.0.0.1
	Domains    []string
	SSLEnabled bool
}

// NoopProxy is used when nginx is absent; the app still deploys.
type NoopProxy struct{}

func (NoopProxy) Configure(context.Context, ProxyConfig) error { return nil }

// Engine executes the deployment pipeline.
type Engine struct {
	Runtime ContainerRuntime
	Git     GitClient
	Health  HealthChecker
	Proxy   ProxyManager
	Sink    EventSink
	Now     func() time.Time
}

// Execute runs the full pipeline: clone → build → start → health check →
// proxy → cleanup (spec §14). The previous release keeps serving until the
// health check passes (spec §17 zero-downtime).
func (e *Engine) Execute(ctx context.Context, req Request) error {
	s := sink{deploymentID: req.DeploymentID, out: e.Sink}
	started := e.now()

	s.emit(map[string]any{"type": "deployment_started"})

	commit, err := e.stageClone(ctx, s, req)
	if err != nil {
		return e.fail(s, req, StageClone, err, started)
	}

	imageRef, err := e.stageBuild(ctx, s, req)
	if err != nil {
		return e.fail(s, req, StageBuild, err, started)
	}

	hostPort, err := e.stageStart(ctx, s, req, imageRef)
	if err != nil {
		return e.fail(s, req, StageStart, err, started)
	}

	if err := e.stageHealthCheck(ctx, s, req, hostPort); err != nil {
		return e.fail(s, req, StageHealthCheck, err, started)
	}

	if err := e.stageProxy(ctx, s, req, hostPort); err != nil {
		return e.fail(s, req, StageProxy, err, started)
	}

	if err := e.stageCleanup(ctx, s, req); err != nil {
		// Cleanup failure must not fail an already-live deployment.
		s.emit(map[string]any{"type": "log", "stream": "system", "line": fmt.Sprintf("cleanup warning: %v", err)})
	}

	emitStageCompleted(s, StageCleanup)
	duration := int(e.now().Sub(started).Seconds())
	s.emit(map[string]any{"type": "deployment_completed", "commit_sha": commit, "duration_seconds": duration})
	return nil
}

func (e *Engine) stageClone(ctx context.Context, s sink, req Request) (string, error) {
	emitStage(s, StageClone)
	if err := e.Git.Checkout(ctx, req.App.RepositoryURL, req.App.Branch, req.CommitSHA, req.App.AppPath); err != nil {
		return "", fmt.Errorf("clone: %w", err)
	}
	commit, err := e.Git.CurrentCommit(ctx, req.App.AppPath)
	if err != nil {
		return "", fmt.Errorf("resolve commit: %w", err)
	}
	emitStageCompleted(s, StageClone)
	return commit, nil
}

func (e *Engine) stageBuild(ctx context.Context, s sink, req Request) (string, error) {
	emitStage(s, StageBuild)
	imageRef := fmt.Sprintf("%s:%s", req.App.ContainerBase, imageTag(req))
	if err := e.Runtime.Build(ctx, req.App.AppPath, imageRef); err != nil {
		return "", fmt.Errorf("build image %s: %w", imageRef, err)
	}
	emitStageCompleted(s, StageBuild)
	return imageRef, nil
}

func (e *Engine) stageStart(ctx context.Context, s sink, req Request, imageRef string) (int, error) {
	emitStage(s, StageStart)
	if req.App.Port == 0 {
		return 0, fmt.Errorf("app port is not configured; the agent deploys containerized apps")
	}
	cfg := RunConfig{
		Name:        candidateName(req.App.ContainerBase),
		Image:       imageRef,
		Port:        req.App.Port,
		Env:         req.App.Env,
		CPULimit:    req.App.CPULimit,
		MemoryLimit: req.App.MemoryLimit,
		Labels:      map[string]string{"deploydock.app": req.App.ContainerBase, "deploydock.role": "candidate"},
	}
	_, hostPort, err := e.Runtime.Run(ctx, cfg)
	if err != nil {
		return 0, fmt.Errorf("start container: %w", err)
	}
	s.emit(map[string]any{"type": "log", "stream": "system", "line": fmt.Sprintf("candidate container live on 127.0.0.1:%d", hostPort)})
	emitStageCompleted(s, StageStart)
	return hostPort, nil
}

func (e *Engine) stageHealthCheck(ctx context.Context, s sink, req Request, hostPort int) error {
	emitStage(s, StageHealthCheck)
	url := healthURL(hostPort, req.App.HealthcheckURL)
	result := e.Health.Check(ctx, url)
	if !result.Passed {
		s.emit(map[string]any{
			"type": "health_check_failed", "status_code": result.StatusCode,
			"error": result.Error,
		})
		return fmt.Errorf("health check failed after %d attempts: %s", result.Attempts, result.Error)
	}
	s.emit(map[string]any{"type": "health_check_passed", "status_code": result.StatusCode})
	emitStageCompleted(s, StageHealthCheck)
	return nil
}

func (e *Engine) stageProxy(ctx context.Context, s sink, req Request, hostPort int) error {
	emitStage(s, StageProxy)
	if e.Proxy == nil {
		e.Proxy = NoopProxy{}
	}
	if err := e.Proxy.Configure(ctx, ProxyConfig{AppName: req.App.ContainerBase, Port: hostPort}); err != nil {
		return fmt.Errorf("proxy: %w", err)
	}
	emitStageCompleted(s, StageProxy)
	return nil
}

// stageCleanup swaps the candidate in as the current release and removes the
// old container: stop old only after the new one is live (spec §17).
func (e *Engine) stageCleanup(ctx context.Context, s sink, req Request) error {
	emitStage(s, StageCleanup)
	current := currentName(req.App.ContainerBase)
	candidate := candidateName(req.App.ContainerBase)

	// Stop the old current (it may not exist on first deploy) to free the name.
	if err := e.Runtime.StopAndRemove(ctx, current); err != nil {
		return fmt.Errorf("stop previous release: %w", err)
	}
	if err := e.Runtime.Rename(ctx, candidate, current); err != nil {
		return fmt.Errorf("promote candidate: %w", err)
	}
	return nil
}

func (e *Engine) fail(s sink, req Request, stage string, cause error, started time.Time) error {
	duration := int(e.now().Sub(started).Seconds())
	s.emit(map[string]any{
		"type": "deployment_failed", "stage": stage,
		"error": cause.Error(), "duration_seconds": duration,
	})
	// Best-effort: remove the candidate so a failed deploy leaves no junk.
	_ = e.Runtime.StopAndRemove(context.Background(), candidateName(req.App.ContainerBase))
	return cause
}

func (e *Engine) now() time.Time {
	if e.Now == nil {
		return time.Now()
	}
	return e.Now()
}

func emitStage(s sink, stage string) {
	s.emit(map[string]any{"type": "stage_started", "stage": stage})
}

func emitStageCompleted(s sink, stage string) {
	s.emit(map[string]any{"type": "stage_completed", "stage": stage})
}

func candidateName(base string) string { return base + "-candidate" }
func currentName(base string) string   { return base + "-current" }

// healthURL joins the published host port with the app's health path.
func healthURL(hostPort int, healthPath string) string {
	if healthPath == "" {
		healthPath = "/"
	}
	if healthPath[0] != '/' {
		healthPath = "/" + healthPath
	}
	return fmt.Sprintf("http://127.0.0.1:%d%s", hostPort, healthPath)
}

func imageTag(req Request) string {
	if req.CommitSHA != "" && len(req.CommitSHA) >= 7 {
		return req.CommitSHA[:7]
	}
	return "latest"
}
