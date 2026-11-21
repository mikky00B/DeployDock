// Package git implements engine.GitClient by shelling out to git.
package git

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
)

// Client is a CLI-backed GitClient.
type Client struct {
	// Bin overrides the git binary (tests); defaults to "git".
	Bin string
}

func (c *Client) binary() string {
	if c.Bin != "" {
		return c.Bin
	}
	return "git"
}

func (c *Client) run(ctx context.Context, dir string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, c.binary(), args...)
	cmd.Dir = dir
	var stderr strings.Builder
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		// Audit H1: repository URLs may embed user:token@ credentials; git
		// error output echoes them. Redact before the error reaches logs,
		// events, or email.
		return string(out), fmt.Errorf("git %s: %w: %s",
			redactArgs(args), err, redactSecrets(strings.TrimSpace(stderr.String())))
	}
	return string(out), nil
}

// redactArgs masks credential-bearing URLs inside the argument echo.
func redactArgs(args []string) string {
	redacted := make([]string, len(args))
	for i, arg := range args {
		redacted[i] = redactSecrets(arg)
	}
	return strings.Join(redacted, " ")
}

// redactSecrets masks user:password@ userinfo in URLs. git's own credential
// helpers never print the password, but a URL passed via argv shows up in
// error output verbatim.
func redactSecrets(text string) string {
	if !strings.Contains(text, "@") {
		return text
	}
 atIndex := strings.Index(text, "://")
	if atIndex < 0 {
		return text
	}
	rest := text[atIndex+3:]
	userEnd := strings.IndexAny(rest, "@")
	if userEnd < 0 {
		return text
	}
	return text[:atIndex+3] + "[REDACTED]@" + rest[userEnd+1:]
}

// Checkout makes workspace hold the requested commit: a fresh clone when the
// directory is empty, otherwise fetch + checkout (spec §14 step 3/4).
func (c *Client) Checkout(ctx context.Context, repoURL, branch, commit, workspace string) error {
	if _, err := os.Stat(workspace + "/.git"); os.IsNotExist(err) {
		if err := os.MkdirAll(workspace, 0o755); err != nil {
			return fmt.Errorf("create workspace: %w", err)
		}
		if _, err := c.run(ctx, workspace, "clone", "--branch", branch, repoURL, "."); err != nil {
			return err
		}
	} else {
		if _, err := c.run(ctx, workspace, "fetch", "--all", "--prune"); err != nil {
			return err
		}
		if _, err := c.run(ctx, workspace, "checkout", branch); err != nil {
			return err
		}
		if _, err := c.run(ctx, workspace, "pull", "--ff-only"); err != nil {
			// A force-pushed branch can break ff-only; a hard reset covers it.
			if _, resetErr := c.run(ctx, workspace, "reset", "--hard", "origin/"+branch); resetErr != nil {
				return err
			}
		}
	}
	if commit != "" {
		if _, err := c.run(ctx, workspace, "checkout", commit); err != nil {
			return fmt.Errorf("checkout %s: %w", commit, err)
		}
	}
	return nil
}

func (c *Client) CurrentCommit(ctx context.Context, workspace string) (string, error) {
	out, err := c.run(ctx, workspace, "rev-parse", "HEAD")
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(out), nil
}
