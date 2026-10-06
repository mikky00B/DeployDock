// Package mcp implements a Model Context Protocol server over stdio for the
// DeployDock CLI (Theme A of v3): AI coding agents (Claude Code, Cursor,
// Codex) operate DeployDock directly — list, deploy, inspect, roll back.
//
// The protocol surface used here is deliberately minimal: JSON-RPC 2.0 over
// stdin/stdout with initialize / tools/list / tools/call / ping. Everything a
// tools/call needs already exists as control-plane HTTP endpoints behind the
// CLI's stored credentials.
package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"

	"github.com/deploydock/deploydock/go/internal/cli"
)

const protocolVersion = "2024-11-05"

// Server is the stdio MCP server. It reads one JSON-RPC message per line and
// writes one response line per request (notifications get no response).
type Server struct {
	API   *cli.API
	In    io.Reader
	Out   io.Writer
	Debug *slog.Logger
}

// Run processes messages until stdin closes or an unrecoverable read error
// occurs. A malformed line is answered with a JSON-RPC error (id null) and
// the loop continues — a chatty or buggy client must not kill the server.
func (s *Server) Run(ctx context.Context) error {
	reader := bufio.NewScanner(s.In)
	reader.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)
	writer := bufio.NewWriter(s.Out)

	for reader.Scan() {
		line := reader.Bytes()
		if len(trimSpace(line)) == 0 {
			continue
		}
		response := s.handle(ctx, line)
		if response == nil {
			continue // notification: no response
		}
		encoded, err := json.Marshal(response)
		if err != nil {
			return fmt.Errorf("encode response: %w", err)
		}
		if _, err := writer.Write(encoded); err != nil {
			return err
		}
		if err := writer.WriteByte('\n'); err != nil {
			return err
		}
		if err := writer.Flush(); err != nil {
			return err
		}
	}
	return reader.Err()
}

func trimSpace(b []byte) []byte {
	start := 0
	for start < len(b) && isSpace(b[start]) {
		start++
	}
	end := len(b)
	for end > start && isSpace(b[end-1]) {
		end--
	}
	return b[start:end]
}

func isSpace(c byte) bool { return c == ' ' || c == '\t' || c == '\r' || c == '\n' }

// handle dispatches one incoming JSON-RPC message and returns the response
// object (nil for notifications).
func (s *Server) handle(ctx context.Context, line []byte) any {
	var request struct {
		JSONRPC string          `json:"jsonrpc"`
		ID      json.RawMessage `json:"id"`
		Method  string          `json:"method"`
		Params  json.RawMessage `json:"params"`
	}
	if err := json.Unmarshal(line, &request); err != nil {
		return errorResponse(nil, -32700, "Parse error: request is not valid JSON")
	}
	if request.JSONRPC != "2.0" && request.JSONRPC != "" {
		return errorResponse(request.ID, -32600, "Invalid Request: jsonrpc must be \"2.0\"")
	}

	switch request.Method {
	case "initialize":
		return resultResponse(request.ID, map[string]any{
			"protocolVersion": protocolVersion,
			"capabilities":    map[string]any{"tools": map[string]any{}},
			"serverInfo":      map[string]any{"name": "deploydock", "version": cli.Version},
		})
	case "notifications/initialized", "notifications/cancelled":
		return nil // notifications: acknowledge silently
	case "ping":
		return resultResponse(request.ID, map[string]any{})
	case "tools/list":
		return resultResponse(request.ID, map[string]any{"tools": ToolDefinitions()})
	case "tools/call":
		return s.callTool(ctx, request.ID, request.Params)
	case "":
		return errorResponse(request.ID, -32600, "Invalid Request: missing method")
	default:
		return errorResponse(request.ID, -32601, fmt.Sprintf("Method not found: %s", request.Method))
	}
}

func errorResponse(id json.RawMessage, code int, message string) map[string]any {
	if len(id) == 0 {
		id = json.RawMessage("null")
	}
	return map[string]any{
		"jsonrpc": "2.0",
		"id":      id,
		"error":   map[string]any{"code": code, "message": message},
	}
}

func resultResponse(id json.RawMessage, result any) map[string]any {
	return map[string]any{"jsonrpc": "2.0", "id": id, "result": result}
}

// callTool executes one tools/call request.
func (s *Server) callTool(ctx context.Context, id json.RawMessage, params json.RawMessage) any {
	var request struct {
		Name      string          `json:"name"`
		Arguments json.RawMessage `json:"arguments"`
	}
	if err := json.Unmarshal(params, &request); err != nil {
		return resultResponse(id, toolError("arguments are not a valid object"))
	}

	definition, ok := ToolByName(request.Name)
	if !ok {
		return resultResponse(id, toolError(fmt.Sprintf("unknown tool: %s", request.Name)))
	}

	arguments := map[string]any{}
	if len(request.Arguments) > 0 {
		if err := json.Unmarshal(request.Arguments, &arguments); err != nil {
			return resultResponse(id, toolError("arguments are not a valid object"))
		}
	}

	output, err := definition.Run(ctx, s.API, arguments)
	if err != nil {
		if os.IsTimeout(err) || ctx.Err() != nil {
			return resultResponse(id, toolError("operation timed out"))
		}
		return resultResponse(id, toolError(err.Error()))
	}
	return resultResponse(id, map[string]any{
		"content": []map[string]any{{"type": "text", "text": output}},
		"isError": false,
	})
}

func toolError(message string) map[string]any {
	return map[string]any{
		"content": []map[string]any{{"type": "text", "text": message}},
		"isError": true,
	}
}
