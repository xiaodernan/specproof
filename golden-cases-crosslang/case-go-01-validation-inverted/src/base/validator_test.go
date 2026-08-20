package validator

import "testing"

func TestEmailAllowedRejectsBlockedDomain(t *testing.T) {
	if EmailAllowed("attacker@evil.com") {
		t.Fatal(`EmailAllowed("attacker@evil.com") = true; want false`)
	}
}

func TestEmailAllowedAcceptsOrdinaryDomain(t *testing.T) {
	if !EmailAllowed("user@example.com") {
		t.Fatal(`EmailAllowed("user@example.com") = false; want true`)
	}
}
