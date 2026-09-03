// deploydock-agent is the DeployDock VPS agent (spec §21-26).
//
// It runs on managed infrastructure, makes outbound connections to the
// FastAPI control plane only, and never exposes a local management port.
//
// Commands:
//
//	deploydock-agent register --server URL --token TOKEN [--name NAME]
//	deploydock-agent run
//	deploydock-agent status
//	deploydock-agent doctor
//	deploydock-agent version
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/deploydock/deploydock/go/internal/agent"
)

func main() {
	log := slog.New(slog.NewTextHandler(os.Stderr, nil))

	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	var err error
	switch os.Args[1] {
	case "register":
		err = cmdRegister(ctx, log, os.Args[2:])
	case "run":
		err = agent.Run(ctx, log)
	case "status":
		err = agent.Status(log)
	case "doctor":
		if !agent.Doctor(ctx, log) {
			os.Exit(1)
		}
	case "version":
		fmt.Println("deploydock-agent " + agent.Version)
	case "help", "-h", "--help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\n\n", os.Args[1])
		usage()
		os.Exit(2)
	}

	if err != nil {
		log.Error("command failed", "command", os.Args[1], "error", err)
		os.Exit(1)
	}
}

func cmdRegister(ctx context.Context, log *slog.Logger, args []string) error {
	flags := flag.NewFlagSet("register", flag.ExitOnError)
	server := flags.String("server", envOrDefault("DEPLOYDOCK_URL", "http://127.0.0.1:8000"), "control plane base URL")
	token := flags.String("token", os.Getenv("DEPLOYDOCK_REGISTRATION_TOKEN"), "registration token (single-use)")
	name := flags.String("name", "", "agent name (defaults to hostname)")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *token == "" {
		return fmt.Errorf("a registration token is required: pass --token or DEPLOYDOCK_REGISTRATION_TOKEN")
	}
	state, err := agent.Register(ctx, *server, *token, *name)
	if err != nil {
		return err
	}
	log.Info("agent registered", "agent_id", state.AgentID, "state_path", "see 'deploydock-agent status'")
	return nil
}

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func usage() {
	fmt.Print(`deploydock-agent — DeployDock VPS agent

Usage:

  deploydock-agent register --server URL --token TOKEN [--name NAME]
  deploydock-agent run
  deploydock-agent status
  deploydock-agent doctor
  deploydock-agent version
`)
}
