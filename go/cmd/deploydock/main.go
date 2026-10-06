// deploydock is the DeployDock developer CLI (spec §28-32).
//
// Usage:
//
//	deploydock login [--url URL] [--email E] [--password P]
//	deploydock logout | whoami
//	deploydock projects [--json]
//	deploydock project create --name N --repo R [--server ID] [--branch B]
//	                         [--path P] [--deploy-command CMD] [--service S]
//	                         [--port N] [--health-path P]
//	deploydock project inspect NAME | project delete NAME
//	deploydock deploy [NAME] [--file deploydock.yaml]
//	deploydock status [--json]
//	deploydock logs NAME [--deployment ID]
//	deploydock rollback NAME [--to DEPLOYMENT_ID]
//	deploydock init
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/deploydock/deploydock/go/internal/cli"
	"github.com/deploydock/deploydock/go/internal/mcp"
)

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	var err error
	switch os.Args[1] {
	case "login":
		flags := flag.NewFlagSet("login", flag.ExitOnError)
		url := flags.String("url", "", "control plane URL")
		email := flags.String("email", "", "account email")
		password := flags.String("password", "", "account password")
		_ = flags.Parse(os.Args[2:])
		err = cli.CmdLogin(ctx, *url, *email, *password)
	case "logout":
		err = cli.CmdLogout(ctx)
	case "whoami":
		err = cli.CmdWhoami(ctx)
	case "projects":
		flags := flag.NewFlagSet("projects", flag.ExitOnError)
		asJSON := flags.Bool("json", false, "machine-readable output")
		_ = flags.Parse(os.Args[2:])
		err = cli.CmdProjects(ctx, *asJSON)
	case "project":
		err = cmdProject(ctx, os.Args[2:])
	case "deploy":
		flags := flag.NewFlagSet("deploy", flag.ExitOnError)
		file := flags.String("file", "", "project config file (default deploydock.yaml)")
		_ = flags.Parse(os.Args[2:])
		name := ""
		if flags.NArg() > 0 {
			name = flags.Arg(0)
		}
		err = cli.CmdDeploy(ctx, name, *file)
	case "status":
		flags := flag.NewFlagSet("status", flag.ExitOnError)
		asJSON := flags.Bool("json", false, "machine-readable output")
		_ = flags.Parse(os.Args[2:])
		err = cli.CmdStatus(ctx, *asJSON)
	case "logs":
		flags := flag.NewFlagSet("logs", flag.ExitOnError)
		deployment := flags.String("deployment", "", "deployment id (default: latest)")
		_ = flags.Parse(os.Args[2:])
		name := ""
		if flags.NArg() > 0 {
			name = flags.Arg(0)
		}
		err = cli.CmdLogs(ctx, name, *deployment)
	case "rollback":
		flags := flag.NewFlagSet("rollback", flag.ExitOnError)
		target := flags.String("to", "", "deployment id to roll back to (default: latest)")
		_ = flags.Parse(os.Args[2:])
		name := ""
		if flags.NArg() > 0 {
			name = flags.Arg(0)
		}
		err = cli.CmdRollback(ctx, name, *target)
	case "mcp":
		err = cmdMCP(ctx, os.Args[2:])
	case "init":
		dir := "."
		if len(os.Args) > 2 {
			dir = os.Args[2]
		}
		err = cli.CmdInit(dir)
	case "version":
		fmt.Println("deploydock v2 (dev)")
	case "help", "-h", "--help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}

	if err != nil {
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func cmdProject(ctx context.Context, args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("usage: deploydock project create|inspect|delete ...")
	}
	switch args[0] {
	case "create":
		flags := flag.NewFlagSet("project create", flag.ExitOnError)
		name := flags.String("name", "", "project name (required)")
		repo := flags.String("repo", "", "repository URL (required)")
		server := flags.String("server", "", "server id (optional when only one server)")
		branch := flags.String("branch", "main", "branch")
		path := flags.String("path", "", "app path on the server")
		deployCommand := flags.String("deploy-command", "", "build/deploy command (required)")
		service := flags.String("service", "", "systemd service name")
		health := flags.String("health-path", "", "HTTP health path")
		port := flags.Int("port", 0, "container port")
		_ = flags.Parse(args[1:])
		if *name == "" || *repo == "" || *deployCommand == "" {
			return fmt.Errorf("--name, --repo and --deploy-command are required")
		}
		return cli.CmdProjectCreate(ctx, *name, *server, *repo, *branch, *path, *deployCommand, *service, *health, *port)
	case "inspect":
		if len(args) < 2 {
			return fmt.Errorf("usage: deploydock project inspect NAME")
		}
		return cli.CmdProjectInspect(ctx, args[1])
	case "delete":
		if len(args) < 2 {
			return fmt.Errorf("usage: deploydock project delete NAME")
		}
		return cli.CmdProjectDelete(ctx, args[1])
	default:
		return fmt.Errorf("unknown project command %q", args[0])
	}
}

// cmdMCP handles `deploydock mcp serve|setup` — v3 Theme A: AI agents
// operate DeployDock through the Model Context Protocol.
func cmdMCP(ctx context.Context, args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("usage: deploydock mcp serve | mcp setup [--agents ...]")
	}
	switch args[0] {
	case "serve":
		config, err := cli.LoadConfig()
		if err != nil {
			return err
		}
		if config.Token == "" {
			return fmt.Errorf("not signed in: run 'deploydock login' first")
		}
		api := cli.NewAPI(config.APIURL, config.Token)
		server := &mcp.Server{API: api, In: os.Stdin, Out: os.Stdout}
		return server.Run(ctx)
	case "setup":
		flags := flag.NewFlagSet("mcp setup", flag.ExitOnError)
		agentsFlag := flags.String("agents", "claude,cursor,codex", "comma-separated agents to register")
		url := flags.String("url", "", "control plane URL (default: stored config)")
		token := flags.String("token", "", "access token (default: stored config)")
		home := flags.String("home", "", "home directory override (for testing)")
		_ = flags.Parse(args[1:])

		config, err := cli.LoadConfig()
		if err != nil {
			return err
		}
		if *url == "" {
			*url = config.APIURL
		}
		if *token == "" {
			*token = config.Token
		}
		if *url == "" || *token == "" {
			return fmt.Errorf("control plane URL and token are required: login first or pass --url/--token")
		}
		entry, err := cli.BuildMCPEntry(*url, *token)
		if err != nil {
			return err
		}
		baseDir := *home
		if baseDir == "" {
			baseDir, err = os.UserHomeDir()
			if err != nil {
				return err
			}
		}
		agentList := strings.Split(*agentsFlag, ",")
		results, err := cli.SetupAgents(baseDir, agentList, entry)
		for _, result := range results {
			fmt.Printf("Registered MCP server with %s.\n", result)
		}
		if err != nil {
			return err
		}
		fmt.Println("DeployDock is now operable from your AI agent: \"list my apps\" or \"deploy watchdog\".")
		return nil
	default:
		return fmt.Errorf("unknown mcp command %q (supported: serve, setup)", args[0])
	}
}

func usage() {
	fmt.Print(`deploydock — DeployDock CLI

Usage:

  deploydock login [--url URL] [--email E] [--password P]
  deploydock logout | whoami
  deploydock projects [--json]
  deploydock project create --name N --repo R [--server ID] [--branch B]
                           [--path P] [--deploy-command CMD] [--port N]
  deploydock project inspect NAME | project delete NAME
  deploydock deploy [NAME]
  deploydock status [--json]
  deploydock logs NAME [--deployment ID]
  deploydock rollback NAME [--to ID]
  deploydock mcp serve | mcp setup [--agents claude,cursor,codex]
  deploydock init
`)
}
