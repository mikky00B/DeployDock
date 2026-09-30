// The CLI commands (spec §29): login/logout/whoami, projects, deploy, status,
// logs, rollback, init. Output is human-readable by default, --json where
// useful (spec §30).
package cli

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
)

// ---- auth ----

func CmdLogin(ctx context.Context, apiURL, email, password string) error {
	if apiURL == "" {
		apiURL = envOr("DEPLOYDOCK_URL", "http://127.0.0.1:8000")
	}
	if email == "" {
		email = envOr("DEPLOYDOCK_EMAIL", "")
	}
	if password == "" {
		password = envOr("DEPLOYDOCK_PASSWORD", "")
	}
	if email == "" || password == "" {
		reader := bufio.NewReader(os.Stdin)
		if email == "" {
			fmt.Print("Email: ")
			line, _ := reader.ReadString('\n')
			email = strings.TrimSpace(line)
		}
		if password == "" {
			fmt.Print("Password: ")
			line, _ := reader.ReadString('\n')
			password = strings.TrimSpace(line)
		}
	}

	api := NewAPI(apiURL, "")
	var response LoginResponse
	if err := api.DoJSON(ctx, "POST", "/api/v1/auth/login", map[string]string{"email": email, "password": password}, &response); err != nil {
		return err
	}
	if err := SaveConfig(&Config{APIURL: apiURL, Token: response.Token.AccessToken}); err != nil {
		return err
	}
	fmt.Printf("Signed in as %s. Credentials stored in the deploydock config.\n", response.User.Email)
	return nil
}

func CmdLogout(ctx context.Context) error {
	config, err := LoadConfig()
	if err != nil {
		return err
	}
	if config.Token != "" {
		api := NewAPI(config.APIURL, config.Token)
		// Server-side revocation is best-effort; the local token goes either way.
		_ = api.DoJSON(ctx, "POST", "/api/v1/auth/logout", nil, nil)
	}
	if err := SaveConfig(&Config{APIURL: config.APIURL, Token: ""}); err != nil {
		return err
	}
	fmt.Println("Signed out.")
	return nil
}

func CmdWhoami(ctx context.Context) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)
	var user User
	if err := api.DoJSON(ctx, "GET", "/api/v1/auth/me", nil, &user); err != nil {
		return err
	}
	fmt.Printf("%s (%s)\n", user.Email, config.APIURL)
	return nil
}

func requireAuth() (*Config, error) {
	config, err := LoadConfig()
	if err != nil {
		return nil, err
	}
	if config.Token == "" {
		return nil, fmt.Errorf("not signed in: run 'deploydock login' first")
	}
	return config, nil
}

// ---- projects ----

func CmdProjects(ctx context.Context, asJSON bool) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)
	var apps []App
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps", nil, &apps); err != nil {
		return err
	}
	if asJSON {
		return json.NewEncoder(os.Stdout).Encode(apps)
	}
	if len(apps) == 0 {
		fmt.Println("No projects yet. Create one with 'deploydock project create'.")
		return nil
	}
	fmt.Printf("%-24s %-8s %-40s %s\n", "NAME", "BRANCH", "REPOSITORY", "COMMIT")
	for _, application := range apps {
		commit := "-"
		if application.CurrentCommit != nil && *application.CurrentCommit != "" {
			commit = (*application.CurrentCommit)[:7]
		}
		fmt.Printf("%-24s %-8s %-40s %s\n", application.Name, application.Branch, application.RepositoryURL, commit)
	}
	return nil
}

// CmdProjectCreate creates a project (spec: projects map to control-plane apps).
func CmdProjectCreate(ctx context.Context, name, serverID, repo, branch, path, deployCommand, serviceName, healthPath string, port int) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)

	if serverID == "" {
		servers, err := listServers(api, ctx)
		if err != nil {
			return err
		}
		if len(servers) == 0 {
			return fmt.Errorf("no servers registered: add one in the dashboard first")
		}
		if len(servers) == 1 {
			serverID = servers[0].ID
			fmt.Printf("Using server %s (%s)\n", servers[0].Name, servers[0].Host)
		} else {
			return fmt.Errorf("multiple servers registered: pass --server <id>")
		}
	}
	if branch == "" {
		branch = "main"
	}
	if path == "" {
		path = "/opt/deploydock/" + name
	}

	payload := AppPayload{Name: name, ServerID: serverID, RepositoryURL: repo, Branch: branch, AppPath: path, DeployCommand: deployCommand, ServiceName: serviceName, HealthcheckURL: healthPath, Port: port}
	var created App
	if err := api.DoJSON(ctx, "POST", "/api/v1/apps", payload, &created); err != nil {
		return err
	}
	fmt.Printf("Project %s created (%s).\n", created.Name, created.ID)
	return nil
}

func CmdProjectInspect(ctx context.Context, nameOrID string) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	application, err := resolveApp(ctx, config, nameOrID)
	if err != nil {
		return err
	}
	fmt.Printf("Name:       %s\n", application.Name)
	fmt.Printf("ID:         %s\n", application.ID)
	fmt.Printf("Repository: %s (%s)\n", application.RepositoryURL, application.Branch)
	fmt.Printf("Path:       %s\n", application.AppPath)
	if application.CurrentCommit != nil {
		fmt.Printf("Commit:     %s\n", *application.CurrentCommit)
	}
	return nil
}

func CmdProjectDelete(ctx context.Context, nameOrID string) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	application, err := resolveApp(ctx, config, nameOrID)
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)
	if err := api.DoJSON(ctx, "DELETE", "/api/v1/apps/"+application.ID, nil, nil); err != nil {
		return err
	}
	fmt.Printf("Project %s deleted.\n", application.Name)
	return nil
}

// ---- deploy (spec §30: stage output, human-readable) ----

func CmdDeploy(ctx context.Context, nameArg, configFile string) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	name := nameArg
	if name == "" {
		project, err := LoadProjectConfig(orDefault(configFile, "deploydock.yaml"))
		if err != nil {
			return fmt.Errorf("pass a project name or run from a directory with deploydock.yaml: %w", err)
		}
		name = project.Name
	}

	api := NewAPI(config.APIURL, config.Token)
	application, err := resolveApp(ctx, config, name)
	if err != nil {
		return err
	}

	fmt.Printf("Deploying %s...\n\n", application.Name)
	var deployment Deployment
	if err := api.DoJSON(ctx, "POST", "/api/v1/apps/"+application.ID+"/deploy", nil, &deployment); err != nil {
		return err
	}

	if err := followDeployment(ctx, api, deployment.ID, os.Stdout); err != nil {
		return err
	}
	return nil
}

// followDeployment consumes the deployment SSE stream, printing stage and log
// events as they arrive (spec §20: streamed agent → control plane → CLI).
func followDeployment(ctx context.Context, api *API, deploymentID string, out io.Writer) error {
	req, err := httpGet(ctx, api, "/api/v1/deployments/"+deploymentID+"/stream")
	if err != nil {
		return err
	}
	defer req.Body.Close()

	reader := bufio.NewScanner(req.Body)
	reader.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	eventType := ""
	for reader.Scan() {
		line := reader.Text()
		switch {
		case strings.HasPrefix(line, "event:"):
			eventType = strings.TrimSpace(strings.TrimPrefix(line, "event:"))
		case strings.HasPrefix(line, "data:"):
			data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
			printSSEEvent(out, eventType, data)
		}
		if err := ctx.Err(); err != nil {
			return nil
		}
	}
	return reader.Err()
}

func printSSEEvent(out io.Writer, eventType, data string) {
	var payload struct {
		Stream string `json:"stream"`
		Line   string `json:"line"`
		Status string `json:"status"`
	}
	_ = json.Unmarshal([]byte(data), &payload)
	switch eventType {
	case "log":
		fmt.Fprintln(out, payload.Line)
	case "status":
		fmt.Fprintf(out, "✓ %s\n", strings.ToUpper(payload.Status))
	case "heartbeat":
		// keepalive — print nothing
	}
}

// ---- status ----

func CmdStatus(ctx context.Context, asJSON bool) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)
	var dashboard Dashboard
	if err := api.DoJSON(ctx, "GET", "/api/v1/dashboard", nil, &dashboard); err != nil {
		return err
	}
	if asJSON {
		return json.NewEncoder(os.Stdout).Encode(dashboard)
	}
	summary := dashboard.Summary
	fmt.Printf("Servers: %d/%d connected\n", summary.ConnectedServers, summary.TotalServers)
	fmt.Printf("Apps:    %d/%d deployed\n", summary.DeployedApps, summary.TotalApps)
	fmt.Printf("Recent failures (7d): %d\n", summary.RecentFailures)
	if summary.LatestDeploymentStatus != nil {
		fmt.Printf("Latest deployment: %s\n", *summary.LatestDeploymentStatus)
	}
	return nil
}

// ---- logs ----

func CmdLogs(ctx context.Context, nameOrID, deploymentID string) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)
	application, err := resolveApp(ctx, config, nameOrID)
	if err != nil {
		return err
	}
	id := deploymentID
	if id == "" {
		id, err = latestDeploymentID(ctx, api, application.ID)
		if err != nil {
			return err
		}
	}
	var logs []DeploymentLog
	if err := api.DoJSON(ctx, "GET", "/api/v1/deployments/"+id+"/logs", nil, &logs); err != nil {
		return err
	}
	for _, log := range logs {
		fmt.Printf("[%s] %s\n", log.Stream, log.Line)
	}
	return nil
}

// ---- rollback ----

func CmdRollback(ctx context.Context, nameOrID, targetDeployment string) error {
	config, err := requireAuth()
	if err != nil {
		return err
	}
	api := NewAPI(config.APIURL, config.Token)
	application, err := resolveApp(ctx, config, nameOrID)
	if err != nil {
		return err
	}
	source := targetDeployment
	if source == "" {
		source, err = latestDeploymentID(ctx, api, application.ID)
		if err != nil {
			return err
		}
	}
	var rollback Deployment
	if err := api.DoJSON(ctx, "POST", "/api/v1/deployments/"+source+"/rollback", nil, &rollback); err != nil {
		return err
	}
	fmt.Printf("Rollback started (deployment %s).\n", rollback.ID)
	return followDeployment(ctx, api, rollback.ID, os.Stdout)
}

// ---- init (spec §32) ----

func CmdInit(dir string) error {
	path := dir + "/deploydock.yaml"
	if _, err := os.Stat(path); err == nil {
		return fmt.Errorf("%s already exists", path)
	}
	name := "my-app"
	healthPath := "/health"
	port := 8080

	if _, err := os.Stat(dir + "/Dockerfile"); err == nil {
		// Docker runtime: keep the defaults.
	} else if _, err := os.Stat(dir + "/go.mod"); err == nil {
		return fmt.Errorf("no Dockerfile found: DeployDock v2 deploys Docker images; add a Dockerfile first")
	} else if _, err := os.Stat(dir + "/package.json"); err == nil {
		return fmt.Errorf("no Dockerfile found: DeployDock v2 deploys Docker images; add a Dockerfile first")
	} else if _, err := os.Stat(dir + "/requirements.txt"); err == nil {
		return fmt.Errorf("no Dockerfile found: DeployDock v2 deploys Docker images; add a Dockerfile first")
	}

	content := fmt.Sprintf("name: %s\n\nbuild:\n  type: docker\n  dockerfile: Dockerfile\n\ndeploy:\n  port: %d\n\nhealth:\n  path: %s\n", name, port, healthPath)
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		return err
	}
	fmt.Printf("Wrote %s — set 'name:' to your project name.\n", path)
	return nil
}

// ---- helpers ----

func listServers(api *API, ctx context.Context) ([]Server, error) {
	var servers []Server
	if err := api.DoJSON(ctx, "GET", "/api/v1/servers", nil, &servers); err != nil {
		return nil, err
	}
	return servers, nil
}

// resolveApp finds an app by UUID or exact name.
func resolveApp(ctx context.Context, config *Config, nameOrID string) (*App, error) {
	api := NewAPI(config.APIURL, config.Token)
	var apps []App
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps", nil, &apps); err != nil {
		return nil, err
	}
	for i := range apps {
		if apps[i].ID == nameOrID || strings.EqualFold(apps[i].Name, nameOrID) {
			return &apps[i], nil
		}
	}
	return nil, fmt.Errorf("project %q not found: run 'deploydock projects' to list", nameOrID)
}

func latestDeploymentID(ctx context.Context, api *API, appID string) (string, error) {
	var deployments []Deployment
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps/"+appID+"/deployments", nil, &deployments); err != nil {
		return "", err
	}
	if len(deployments) == 0 {
		return "", fmt.Errorf("this project has no deployments yet")
	}
	return deployments[0].ID, nil // listed newest-first by the API
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func orDefault(value, fallback string) string {
	if value != "" {
		return value
	}
	return fallback
}
