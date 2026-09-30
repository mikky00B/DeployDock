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
	"syscall"

	"github.com/deploydock/deploydock/go/internal/cli"
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
  deploydock init
`)
}
