package mcp

import "github.com/deploydock/deploydock/go/internal/cli"

// NewTestAPI builds an API client pointed at an arbitrary base URL (usually a
// test stub).
func NewTestAPI(baseURL string) *cli.API {
	return cli.NewAPI(baseURL, "test-token")
}
