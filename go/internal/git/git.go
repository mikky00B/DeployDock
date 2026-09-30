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
		return string(out), fmt.Errorf("git %s: %w: %s",
			strings.Join(args, " "), err, strings.TrimSpace(stderr.String()))
	}
	return string(out), nil
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
