// Package confwrite holds the managed-config primitives shared by the proxy
// managers (nginx, caddy): read-before-overwrite, atomic writes, and restore
// on failed validation. Every proxy manager must keep the file on disk
// consistent with what the server is serving — a failed config change rolls
// back instead of deleting the previous configuration.
package confwrite

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
)

// ReadIfExists returns the file content and whether it existed.
func ReadIfExists(path string) ([]byte, bool, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return data, true, nil
}

// Restore puts back the content captured before an overwrite: the previous
// content when there was one, nothing at all when the file did not exist yet.
func Restore(path string, previous []byte, hadPrevious bool) error {
	if !hadPrevious {
		return os.Remove(path)
	}
	return WriteAtomic(path, previous, 0o644)
}

// WriteAtomic writes via a temp file in the same directory plus rename, so a
// concurrent reload never observes a half-written config.
func WriteAtomic(path string, data []byte, perm fs.FileMode) error {
	tmp, err := os.CreateTemp(filepath.Dir(path), ".deploydock-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName) // no-op once the rename succeeded
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Chmod(perm); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpName, path)
}
