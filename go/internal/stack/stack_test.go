package stack

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeFile(t *testing.T, dir, name, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(filepath.Join(dir, name)), 0o755); err != nil {
		t.Fatalf("mkdir for %s: %v", name, err)
	}
	if err := os.WriteFile(filepath.Join(dir, name), []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", name, err)
	}
}

func TestEnsureDockerfileGeneratesPerStack(t *testing.T) {
	cases := []struct {
		name     string
		files    map[string]string
		wantText string // a marker the generated file must contain
	}{
		{
			name:     "go",
			files:    map[string]string{"go.mod": "module example.com/app\n"},
			wantText: "go build -o /out/app .",
		},
		{
			name:     "go with cmd/server",
			files:    map[string]string{"go.mod": "module example.com/app\n", filepath.Join("cmd", "server") + "/main.go": "package main\n"},
			wantText: "go build -o /out/app ./cmd/server",
		},
		{
			name:     "node",
			files:    map[string]string{"package.json": `{"name":"a","scripts":{"start":"node server.js"}}`},
			wantText: `CMD ["npm", "start"]`,
		},
		{
			name:     "fastapi",
			files:    map[string]string{"requirements.txt": "fastapi\nuvicorn\n", "main.py": "app = 1\n"},
			wantText: `"uvicorn", "main:app"`,
		},
		{
			name:     "fastapi in app package",
			files:    map[string]string{"pyproject.toml": "[project]\n", filepath.Join("app", "main.py"): "app = 1\n"},
			wantText: `"uvicorn", "app.main:app"`,
		},
		{
			name:     "django",
			files:    map[string]string{"requirements.txt": "django\n", "manage.py": "", filepath.Join("config", "settings.py"): ""},
			wantText: "gunicorn config.wsgi:application",
		},
		{
			name:     "static",
			files:    map[string]string{"index.html": "<html></html>"},
			wantText: "/usr/share/nginx/html",
		},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			dir := t.TempDir()
			for name, content := range testCase.files {
				writeFile(t, dir, name, content)
			}

			stack, generated, err := Provisioner{}.EnsureDockerfile(t.Context(), dir, 8080)
			if err != nil || !generated {
				t.Fatalf("EnsureDockerfile() = %q, %v, %v; want generated", stack, generated, err)
			}
			data, err := os.ReadFile(filepath.Join(dir, "Dockerfile"))
			if err != nil {
				t.Fatalf("read generated Dockerfile: %v", err)
			}
			if !strings.Contains(string(data), testCase.wantText) {
				t.Errorf("Dockerfile for %q lacks %q:\n%s", testCase.name, testCase.wantText, data)
			}
			if !strings.Contains(string(data), "8080") {
				t.Errorf("Dockerfile for %q must bake in the app port:\n%s", testCase.name, data)
			}
		})
	}
}

func TestEnsureDockerfileUserFileAlwaysWins(t *testing.T) {
	dir := t.TempDir()
	writeFile(t, dir, "Dockerfile", "FROM alpine\n")
	writeFile(t, dir, "package.json", "{}")

	stack, generated, err := Provisioner{}.EnsureDockerfile(t.Context(), dir, 8080)
	if err != nil || generated || stack != "" {
		t.Fatalf("EnsureDockerfile() = %q, %v, %v; want untouched user Dockerfile", stack, generated, err)
	}
	data, err := os.ReadFile(filepath.Join(dir, "Dockerfile"))
	if err != nil {
		t.Fatalf("read Dockerfile: %v", err)
	}
	if string(data) != "FROM alpine\n" {
		t.Errorf("user Dockerfile was modified: %q", data)
	}
}

func TestEnsureDockerfileUnknownStackIsASilentSkip(t *testing.T) {
	dir := t.TempDir()
	writeFile(t, dir, "README.md", "nothing recognizable")

	stack, generated, err := Provisioner{}.EnsureDockerfile(t.Context(), dir, 8080)
	if err != nil || generated || stack != "" {
		t.Fatalf("EnsureDockerfile() = %q, %v, %v; want empty skip", stack, generated, err)
	}
	if _, err := os.Stat(filepath.Join(dir, "Dockerfile")); !os.IsNotExist(err) {
		t.Errorf("no Dockerfile must be written for an unknown stack")
	}
}

func TestEnsureDockerfileNoopWhenOneExists(t *testing.T) {
	dir := t.TempDir()
	writeFile(t, dir, "go.mod", "module example.com/app\n")
	writeFile(t, dir, "Dockerfile", "FROM golang\n")

	_, generated, err := Provisioner{}.EnsureDockerfile(t.Context(), dir, 8080)
	if err != nil || generated {
		t.Fatalf("EnsureDockerfile() generated=%v err=%v; want no-op", generated, err)
	}
}
