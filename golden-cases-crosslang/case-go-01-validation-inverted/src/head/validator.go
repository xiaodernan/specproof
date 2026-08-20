// Package validator implements the registration email policy.
// Head revision: the blocklist guard is inverted (regression).
package validator

// blockedDomains lists domains that may never register.
var blockedDomains = map[string]bool{
	"evil.com": true,
}

// EmailAllowed reports whether the given email address may be registered.
func EmailAllowed(email string) bool {
	return blockedDomains[domainOf(email)]
}

// domainOf returns the part of the address after the last '@' ("" if none).
func domainOf(email string) string {
	for i := len(email) - 1; i >= 0; i-- {
		if email[i] == '@' {
			return email[i+1:]
		}
	}
	return email
}
