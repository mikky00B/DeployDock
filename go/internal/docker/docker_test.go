package docker

import "testing"

func TestParseHostPort(t *testing.T) {
	cases := []struct {
		name    string
		output  string
		want    int
		wantErr bool
	}{
		{
			name:   "single mapping",
			output: "8080/tcp -> 127.0.0.1:32771\n",
			want:   32771,
		},
		{
			name:   "ipv6 and ipv4 lines, ipv4 wins",
			output: "8080/tcp -> [::]:32772\n8080/tcp -> 127.0.0.1:32772\n",
			want:   32772,
		},
		{
			name:    "no 127.0.0.1 mapping",
			output:  "8080/tcp -> 0.0.0.0:32773\n",
			wantErr: true,
		},
		{
			name:    "empty output",
			output:  "",
			wantErr: true,
		},
		{
			name:    "garbage after the separator",
			output:  "8080/tcp -> 127.0.0.1:not-a-port\n",
			wantErr: true,
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			got, err := parseHostPort(testCase.output)
			if testCase.wantErr {
				if err == nil {
					t.Fatalf("parseHostPort(%q) = %d, want error", testCase.output, got)
				}
				return
			}
			if err != nil {
				t.Fatalf("parseHostPort(%q) error = %v", testCase.output, err)
			}
			if got != testCase.want {
				t.Errorf("parseHostPort(%q) = %d, want %d", testCase.output, got, testCase.want)
			}
		})
	}
}
