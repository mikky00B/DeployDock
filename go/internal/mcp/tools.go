package mcp

import (
	"context"
	"fmt"
	"strings"

	"github.com/deploydock/deploydock/go/internal/cli"
)

// Version is overridden at build time via -ldflags; reported in initialize.
var Version = "dev"

// Tool is one MCP tool: a name, a description for the model, a JSON Schema
// for its arguments, and the function that executes it against the
// control-plane API.
type Tool struct {
	Name        string
	Description string
	InputSchema map[string]any
	Run         func(ctx context.Context, api *cli.API, args map[string]any) (string, error)
}

func stringArg(args map[string]any, key string) (string, error) {
	value, ok := args[key]
	if !ok || value == nil {
		return "", fmt.Errorf("missing required argument: %s", key)
	}
	text, ok := value.(string)
	if !ok || strings.TrimSpace(text) == "" {
		return "", fmt.Errorf("argument %s must be a non-empty string", key)
	}
	return strings.TrimSpace(text), nil
}

func objectSchema(properties map[string]any, required []string) map[string]any {
	schema := map[string]any{
		"type":       "object",
		"properties": properties,
	}
	if len(required) > 0 {
		schema["required"] = required
	}
	return schema
}

// Tools is the v3.1 tool set. Mutating tools say so in their descriptions so
// MCP clients surface a confirmation prompt before executing them.
func Tools() []Tool {
	return []Tool{
		{
			Name:        "list_servers",
			Description: "List the DeployDock servers registered by this account, with connection status.",
			InputSchema: objectSchema(nil, nil),
			Run:         runListServers,
		},
		{
			Name:        "list_apps",
			Description: "List registered apps with their repository, branch, server, and current commit.",
			InputSchema: objectSchema(nil, nil),
			Run:         runListApps,
		},
		{
			Name:        "get_dashboard",
			Description: "Deployment overview: connected servers, deployed apps, recent failures.",
			InputSchema: objectSchema(nil, nil),
			Run:         runDashboard,
		},
		{
			Name:        "deploy_app",
			Description: "MUTATING: start a deployment of an app by name or id. Returns the deployment id and initial status; use get_latest_deployment_logs to follow output.",
			InputSchema: objectSchema(
				map[string]any{"app": map[string]any{"type": "string", "description": "App name or id"}},
				[]string{"app"},
			),
			Run: runDeployApp,
		},
		{
			Name:        "get_deployment",
			Description: "Deployment detail by id: status, kind, commit, duration, error, health-check result.",
			InputSchema: objectSchema(
				map[string]any{"deployment_id": map[string]any{"type": "string"}},
				[]string{"deployment_id"},
			),
			Run: runGetDeployment,
		},
		{
			Name:        "get_latest_deployment_logs",
			Description: "Log lines of the newest deployment for an app.",
			InputSchema: objectSchema(
				map[string]any{"app": map[string]any{"type": "string", "description": "App name or id"}},
				[]string{"app"},
			),
			Run: runLatestLogs,
		},
		{
			Name:        "rollback",
			Description: "MUTATING: roll an app back to its most recent successful release.",
			InputSchema: objectSchema(
				map[string]any{"app": map[string]any{"type": "string", "description": "App name or id"}},
				[]string{"app"},
			),
			Run: runRollback,
		},
		{
			Name:        "cancel_deployment",
			Description: "MUTATING: cancel a non-terminal deployment by id.",
			InputSchema: objectSchema(
				map[string]any{"deployment_id": map[string]any{"type": "string"}},
				[]string{"deployment_id"},
			),
			Run: runCancel,
		},
	}
}

// ToolDefinitions renders the tools for the MCP tools/list response.
func ToolDefinitions() []map[string]any {
	definitions := make([]map[string]any, 0, 8)
	for _, tool := range Tools() {
		definitions = append(definitions, map[string]any{
			"name":        tool.Name,
			"description": tool.Description,
			"inputSchema": tool.InputSchema,
		})
	}
	return definitions
}

// ToolByName looks up one tool.
func ToolByName(name string) (Tool, bool) {
	for _, tool := range Tools() {
		if tool.Name == name {
			return tool, true
		}
	}
	return Tool{}, false
}

// ---- implementations ----

func runListServers(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	var servers []cli.Server
	if err := api.DoJSON(ctx, "GET", "/api/v1/servers", nil, &servers); err != nil {
		return "", err
	}
	if len(servers) == 0 {
		return "No servers registered.", nil
	}
	var out strings.Builder
	for _, server := range servers {
		fmt.Fprintf(&out, "%s — %s@%s:%d [%s]\n", server.Name, server.Username, server.Host, server.Port, server.Status)
	}
	return out.String(), nil
}

func runListApps(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	var apps []cli.App
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps", nil, &apps); err != nil {
		return "", err
	}
	if len(apps) == 0 {
		return "No apps registered.", nil
	}
	var out strings.Builder
	for _, application := range apps {
		commit := "-"
		if application.CurrentCommit != nil && *application.CurrentCommit != "" {
			commit = (*application.CurrentCommit)[:7]
		}
		port := "-"
		if application.Port != nil && *application.Port != 0 {
			port = fmt.Sprintf("%d", *application.Port)
		}
		fmt.Fprintf(&out, "%s (id %s) — %s [%s] commit %s, container port %s\n",
			application.Name, application.ID, application.RepositoryURL, application.Branch, commit, port)
	}
	return out.String(), nil
}

func runDashboard(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	var dashboard cli.Dashboard
	if err := api.DoJSON(ctx, "GET", "/api/v1/dashboard", nil, &dashboard); err != nil {
		return "", err
	}
	summary := dashboard.Summary
	latest := "none"
	if summary.LatestDeploymentStatus != nil {
		latest = *summary.LatestDeploymentStatus
	}
	return fmt.Sprintf("Servers: %d/%d connected. Apps deployed: %d/%d. Recent failures (7d): %d. Latest deployment: %s.",
		summary.ConnectedServers, summary.TotalServers,
		summary.DeployedApps, summary.TotalApps,
		summary.RecentFailures, latest), nil
}

func resolveAppID(ctx context.Context, api *cli.API, nameOrID string) (string, string, error) {
	var apps []cli.App
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps", nil, &apps); err != nil {
		return "", "", err
	}
	for _, application := range apps {
		if application.ID == nameOrID || strings.EqualFold(application.Name, nameOrID) {
			return application.ID, application.Name, nil
		}
	}
	return "", "", fmt.Errorf("app %q not found; use list_apps to see registered apps", nameOrID)
}

func runDeployApp(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	nameOrID, err := stringArg(args, "app")
	if err != nil {
		return "", err
	}
	appID, appName, err := resolveAppID(ctx, api, nameOrID)
	if err != nil {
		return "", err
	}
	var deployment cli.Deployment
	if err := api.DoJSON(ctx, "POST", "/api/v1/apps/"+appID+"/deploy", nil, &deployment); err != nil {
		return "", err
	}
	return fmt.Sprintf("Deployment %s started for %s (status: %s). Follow with get_latest_deployment_logs.", deployment.ID, appName, deployment.Status), nil
}

func runGetDeployment(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	deploymentID, err := stringArg(args, "deployment_id")
	if err != nil {
		return "", err
	}
	var deployment cli.Deployment
	if err := api.DoJSON(ctx, "GET", "/api/v1/deployments/"+deploymentID, nil, &deployment); err != nil {
		return "", err
	}
	out := fmt.Sprintf("Deployment %s — %s (%s), commit %s",
		deployment.ID, deployment.Status, deployment.Kind, pointerOr(deployment.CommitSHA, "-"))
	if deployment.Error != nil && *deployment.Error != "" {
		out += "\nError: " + *deployment.Error
	}
	return out, nil
}

func runLatestLogs(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	nameOrID, err := stringArg(args, "app")
	if err != nil {
		return "", err
	}
	appID, appName, err := resolveAppID(ctx, api, nameOrID)
	if err != nil {
		return "", err
	}
	var deployments []cli.Deployment
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps/"+appID+"/deployments", nil, &deployments); err != nil {
		return "", err
	}
	if len(deployments) == 0 {
		return fmt.Sprintf("No deployments yet for %s.", appName), nil
	}
	var logs []cli.DeploymentLog
	if err := api.DoJSON(ctx, "GET", "/api/v1/deployments/"+deployments[0].ID+"/logs", nil, &logs); err != nil {
		return "", err
	}
	var out strings.Builder
	fmt.Fprintf(&out, "Latest deployment for %s: %s [%s]\n", appName, deployments[0].ID, deployments[0].Status)
	for _, log := range logs {
		fmt.Fprintf(&out, "[%s] %s\n", log.Stream, log.Line)
	}
	return out.String(), nil
}

func runRollback(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	nameOrID, err := stringArg(args, "app")
	if err != nil {
		return "", err
	}
	appID, appName, err := resolveAppID(ctx, api, nameOrID)
	if err != nil {
		return "", err
	}
	latestID, err := latestDeploymentID(ctx, api, appID)
	if err != nil {
		return "", err
	}
	var rollback cli.Deployment
	if err := api.DoJSON(ctx, "POST", "/api/v1/deployments/"+latestID+"/rollback", nil, &rollback); err != nil {
		return "", err
	}
	return fmt.Sprintf("Rollback started for %s (deployment %s, status %s).", appName, rollback.ID, rollback.Status), nil
}

func runCancel(ctx context.Context, api *cli.API, args map[string]any) (string, error) {
	deploymentID, err := stringArg(args, "deployment_id")
	if err != nil {
		return "", err
	}
	var deployment cli.Deployment
	if err := api.DoJSON(ctx, "POST", "/api/v1/deployments/"+deploymentID+"/cancel", nil, &deployment); err != nil {
		return "", err
	}
	return fmt.Sprintf("Deployment %s is now %s.", deployment.ID, deployment.Status), nil
}

func latestDeploymentID(ctx context.Context, api *cli.API, appID string) (string, error) {
	var deployments []cli.Deployment
	if err := api.DoJSON(ctx, "GET", "/api/v1/apps/"+appID+"/deployments", nil, &deployments); err != nil {
		return "", err
	}
	if len(deployments) == 0 {
		return "", fmt.Errorf("this app has no deployments yet")
	}
	return deployments[0].ID, nil // newest first
}

func pointerOr(value *string, fallback string) string {
	if value == nil || *value == "" {
		return fallback
	}
	return *value
}
