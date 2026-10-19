#include <algorithm>
#include <cctype>
#include <cstring>
#include <string>
#include <vector>

#include <git2/sys/errors.h>

#include "git_callbacks.h"
#include "git_plugin.h"

#include "godot_cpp/godot.hpp"
#include "godot_cpp/variant/utility_functions.hpp"

namespace {
constexpr size_t maximum_output_bytes = 1024 * 1024;

int hex_digit(unsigned char c) {
	if (c >= '0' && c <= '9') {
		return c - '0';
	}
	c = static_cast<unsigned char>(std::tolower(c));
	return c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

std::string percent_decode(const std::string &value) {
	std::string decoded;
	decoded.reserve(value.size());
	for (size_t i = 0; i < value.size(); ++i) {
		if (value[i] == '%' && i + 2 < value.size() && hex_digit(value[i + 1]) >= 0 && hex_digit(value[i + 2]) >= 0) {
			decoded += static_cast<char>(hex_digit(value[i + 1]) * 16 + hex_digit(value[i + 2]));
			i += 2;
		} else {
			decoded += value[i];
		}
	}
	return decoded;
}

std::string lowercase(std::string value) {
	std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
	return value;
}

bool secret_query_name(const std::string &name) {
	const std::string decoded = lowercase(percent_decode(name));
	return decoded == "token" || decoded == "access_token" || decoded == "api_key" || decoded == "apikey" || decoded == "key" || decoded == "password" || decoded == "passwd" || decoded == "pass" || decoded == "secret" || decoded == "client_secret" || decoded == "auth" || decoded == "private_token" || decoded == "sig" || decoded == "signature";
}

struct UrlParts {
	std::string scheme;
	std::string authority;
	size_t query = std::string::npos;
	bool uri = false;
};

// Split raw delimiters before percent decoding, as libgit2 does. A colon
// after a slash belongs to a local path; scp paths have no URI query.
UrlParts split_url(const std::string &value) {
	UrlParts parts;
	const size_t colon = value.find(':');
	if (colon == std::string::npos) {
		return parts;
	}
	if (value.compare(colon, 3, "://") == 0) {
		if (colon == 0 || !std::isalpha(static_cast<unsigned char>(value[0]))) {
			return parts;
		}
		for (size_t i = 1; i < colon; ++i) {
			if (!std::isalnum(static_cast<unsigned char>(value[i])) && value[i] != '+' && value[i] != '.' && value[i] != '-') {
				return parts;
			}
		}
		parts.uri = true;
		parts.scheme = lowercase(value.substr(0, colon));
		const size_t end = value.find_first_of("/?#", colon + 3);
		parts.authority = value.substr(colon + 3, end == std::string::npos ? end : end - colon - 3);
		const size_t query = value.find('?', end);
		const size_t fragment = value.find('#', end);
		if (query != std::string::npos && (fragment == std::string::npos || query < fragment)) {
			parts.query = query;
		}
		return parts;
	}
	const size_t slash = value.find_first_of("/\\");
	if (slash != std::string::npos && slash < colon) {
		return parts;
	}
	const size_t at = value.find('@');
	const size_t host_start = at != std::string::npos && at < colon ? at + 1 : 0;
	size_t separator = colon;
	if (value[host_start] == '[') {
		const size_t close = value.find(']', host_start);
		if (close == std::string::npos || close + 1 >= value.size() || value[close + 1] != ':') {
			return parts;
		}
		separator = close + 1;
	}
	parts.scheme = "ssh";
	parts.authority = value.substr(0, separator);
	return parts;
}

bool has_secret_query(const std::string &value, size_t query) {
	const size_t fragment = value.find('#', query);
	const size_t end = fragment == std::string::npos ? value.size() : fragment;
	for (size_t start = query + 1; start < end;) {
		size_t next = value.find('&', start);
		next = next == std::string::npos || next > end ? end : next;
		size_t equals = start;
		while (equals < next && value[equals] != '=') {
			++equals;
		}
		if (equals < next && secret_query_name(value.substr(start, equals - start))) {
			return true;
		}
		start = next + 1;
	}
	return false;
}

CredentialOrigin credential_origin(const godot::String &url, const CredentialOrigin *expected = nullptr) {
	const godot::CharString encoded = url.utf8();
	if (encoded.length() > maximum_output_bytes) {
		return {};
	}
	const UrlParts parts = split_url(std::string(encoded.get_data(), encoded.length()));
	CredentialOrigin origin;
	origin.scheme = parts.scheme;
	if (origin.scheme != "http" && origin.scheme != "https" && origin.scheme != "ssh") {
		return {};
	}
	std::string authority = parts.authority;
	const size_t at = authority.rfind('@');
	if (at != std::string::npos) {
		authority.erase(0, at + 1);
	}
	const std::string default_port = origin.scheme == "https" ? "443" : (origin.scheme == "http" ? "80" : "22");
	origin.port = default_port;
	if (!authority.empty() && authority[0] == '[') {
		const size_t close = authority.find(']');
		if (close == std::string::npos || (close + 1 < authority.size() && authority[close + 1] != ':')) {
			return {};
		}
		origin.host = authority.substr(1, close - 1);
		if (close + 2 < authority.size()) {
			origin.port = authority.substr(close + 2);
		}
	} else if (std::count(authority.begin(), authority.end(), ':') > 1) {
		// libgit2's credential callback formats IPv6 without brackets. Decode
		// that spelling only against the already parsed configured origin.
		authority = lowercase(percent_decode(authority));
		if (expected == nullptr || expected->scheme != origin.scheme) {
			return {};
		}
		if (authority == expected->host) {
			origin.host = authority;
		} else if (authority == expected->host + ":" + expected->port) {
			origin.host = expected->host;
			origin.port = expected->port;
		} else {
			return {};
		}
	} else {
		const size_t colon = authority.find(':');
		origin.host = authority.substr(0, colon);
		if (colon != std::string::npos && colon + 1 < authority.size()) {
			origin.port = authority.substr(colon + 1);
		}
	}
	origin.host = lowercase(percent_decode(origin.host));
	if (!origin.host.empty() && origin.host.back() == '.') {
		origin.host.pop_back();
	}
	if (origin.host.empty()) {
		return {};
	}
	for (unsigned char c : origin.host) {
		if (!std::isalnum(c) && c != ':' && c != '.' && c != '-' && c != '_') {
			return {};
		}
	}
	unsigned int port = 0;
	for (unsigned char c : origin.port) {
		if (c < '0' || c > '9' || (port = port * 10 + c - '0') > 65535) {
			return {};
		}
	}
	origin.port = std::to_string(port);
	return origin;
}

// Store interval ends at their original offsets. A single forward sweep
// merges all overlapping intervals, including overlaps between credentials.
void mark_secret(std::vector<size_t> &ends, const std::string &text, const godot::String &secret) {
	const godot::CharString encoded = secret.utf8();
	const std::string value(encoded.get_data(), encoded.length());
	if (value.empty() || value.size() > text.size()) {
		return;
	}
	// KMP keeps repeated prefixes and overlapping matches linear.
	std::vector<size_t> prefix(value.size(), 0);
	for (size_t i = 1, j = 0; i < value.size(); ++i) {
		while (j && value[i] != value[j]) {
			j = prefix[j - 1];
		}
		if (value[i] == value[j]) {
			++j;
		}
		prefix[i] = j;
	}
	for (size_t i = 0, j = 0; i < text.size(); ++i) {
		while (j && text[i] != value[j]) {
			j = prefix[j - 1];
		}
		if (text[i] == value[j]) {
			++j;
		}
		if (j == value.size()) {
			const size_t start = i + 1 - j;
			ends[start] = std::max(ends[start], i + 1);
			j = prefix[j - 1];
		}
	}
}

bool output_separator(unsigned char c) {
	return std::isspace(c) || c == '\'' || c == '"';
}
} // namespace

godot::String sanitize_git_output(const godot::String &text, const Credentials *credentials) noexcept {
	try {
		if (text.length() > maximum_output_bytes) {
			return {};
		}
		const godot::CharString encoded = text.utf8();
		if (encoded.length() > maximum_output_bytes) {
			return {};
		}
		const std::string original(encoded.get_data(), encoded.length());
		std::vector<size_t> ends(original.size(), 0);
		if (credentials != nullptr) {
			mark_secret(ends, original, credentials->username);
			mark_secret(ends, original, credentials->password);
			mark_secret(ends, original, credentials->ssh_passphrase);
			mark_secret(ends, original, credentials->ssh_public_key_path);
			mark_secret(ends, original, credentials->ssh_private_key_path);
		}
		for (size_t start = 0; start < original.size();) {
			if (output_separator(original[start])) {
				++start;
				continue;
			}
			size_t end = start;
			while (end < original.size() && !output_separator(original[end])) {
				++end;
			}
			const std::string token = original.substr(start, end - start);
			const size_t scheme = token.find("://");
			const size_t authority = scheme == std::string::npos ? 0 : scheme + 3;
			const size_t authority_end = token.find_first_of("/?#", authority);
			const size_t at = token.rfind('@', authority_end == std::string::npos ? token.size() : authority_end);
			if (at != std::string::npos && at >= authority && (scheme != std::string::npos || token.find(':', at) != std::string::npos)) {
				ends[start + authority] = std::max(ends[start + authority], start + at);
			}
			// Diagnostics are unstructured: conservatively redact query-like
			// secrets even in text that is not a configured remote URI.
			for (size_t i = 0; i < token.size(); ++i) {
				if (token[i] != '?' && token[i] != '&') {
					continue;
				}
				const size_t name = i + 1;
				size_t equals = name;
				while (equals < token.size() && token[equals] != '=' && token[equals] != '&' && token[equals] != '?' && token[equals] != '#') {
					++equals;
				}
				i = equals;
				if (equals == token.size() || token[equals] != '=') {
					if (equals < token.size() && (token[equals] == '?' || token[equals] == '&')) {
						--i;
					}
					continue;
				}
				const size_t value = equals + 1;
				const size_t stop = token.find_first_of("&#", value);
				const size_t value_end = stop == std::string::npos ? token.size() : stop;
				if (value < value_end && secret_query_name(token.substr(name, equals - name))) {
					ends[start + value] = std::max(ends[start + value], start + value_end);
				}
				i = value_end - 1;
			}
			start = end;
		}
		std::string sanitized;
		sanitized.reserve(original.size());
		for (size_t i = 0; i < original.size();) {
			if (ends[i] > i) {
				size_t end = ends[i];
				while (++i < end) {
					end = std::max(end, ends[i]);
				}
				sanitized += "[redacted]";
			} else {
				sanitized += original[i++];
			}
		}
		return godot::String::utf8(sanitized.c_str(), sanitized.length());
	} catch (...) {
		// Allocation or conversion failure must never disclose the original.
		return {};
	}
}

bool git_url_contains_credentials(const godot::String &url) noexcept {
	try {
		const godot::CharString encoded = url.utf8();
		if (encoded.length() > maximum_output_bytes) {
			return true;
		}
		const std::string value(encoded.get_data(), encoded.length());
		const UrlParts parts = split_url(value);
		if (parts.scheme.empty()) {
			return false;
		}
		const size_t at = parts.authority.rfind('@');
		if (at != std::string::npos && (parts.scheme != "ssh" || parts.authority.substr(0, at).find(':') != std::string::npos)) {
			return true;
		}
		if (!parts.uri) {
			// Also reject the invalid password-bearing scp spelling rather
			// than letting it masquerade as a host plus repository path.
			const size_t colon = value.find(':');
			const size_t path_at = value.find('@', colon);
			if (parts.authority.find('[') == std::string::npos && path_at != std::string::npos && value.find(':', path_at) != std::string::npos) {
				return true;
			}
		}
		return parts.uri && (parts.scheme == "http" || parts.scheme == "https") && parts.query != std::string::npos && has_secret_query(value, parts.query);
	} catch (...) {
		return true;
	}
}

const char *git_remote_directional_url(const git_remote *remote, git_direction direction) {
	const char *url = direction == GIT_DIRECTION_PUSH ? git_remote_pushurl(remote) : nullptr;
	return url != nullptr ? url : git_remote_url(remote);
}

RemoteOperation::RemoteOperation(const Credentials *p_credentials, const char *url) :
		credentials(p_credentials), origin(credential_origin(url != nullptr ? godot::String::utf8(url) : godot::String())) {}

RemoteOperation::~RemoteOperation() {
	flush_progress();
}

void RemoteOperation::flush_progress() {
	try {
		if (progress_overflow) {
			godot::UtilityFunctions::print("remote: [overlong progress line omitted]");
		} else if (!progress_line.empty()) {
			godot::UtilityFunctions::print("remote: ", sanitize_git_output(godot::String::utf8(progress_line.data(), progress_line.size()).strip_edges(), credentials));
		}
		progress_line.clear();
		progress_overflow = false;
	} catch (...) {
		progress_line.clear();
		progress_overflow = false;
	}
}

extern "C" int progress_cb(const char *str, int len, void *data) {
	try {
		RemoteOperation *operation = static_cast<RemoteOperation *>(data);
		for (int i = 0; i < len; ++i) {
			if (str[i] == '\r' || str[i] == '\n') {
				if (!(str[i] == '\n' && operation->progress_cr)) {
					operation->flush_progress();
				}
				operation->progress_cr = str[i] == '\r';
			} else {
				operation->progress_cr = false;
				if (operation->progress_overflow) {
					continue;
				}
				if (operation->progress_line.size() == 65536) {
					operation->progress_line.clear();
					operation->progress_overflow = true;
				} else {
					operation->progress_line += str[i];
				}
			}
		}
		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int update_cb(const char *refname, const git_oid *a, const git_oid *b, void *data) {
	try {
		constexpr int short_commit_length = 8;
		char a_str[short_commit_length + 1];
		char b_str[short_commit_length + 1];
		const Credentials *credentials = static_cast<RemoteOperation *>(data)->credentials;
		const godot::String safe_refname = sanitize_git_output(godot::String::utf8(refname), credentials);

		git_oid_tostr(b_str, short_commit_length, b);
		if (git_oid_is_zero(a)) {
			godot::UtilityFunctions::print("* [new] ", godot::String::utf8(b_str), " ", safe_refname);
		} else {
			git_oid_tostr(a_str, short_commit_length, a);
			godot::UtilityFunctions::print("[updated] ", godot::String::utf8(a_str), "...", godot::String::utf8(b_str), " ", safe_refname);
		}

		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int transfer_progress_cb(const git_indexer_progress *stats, void *payload) {
	try {
		(void)payload;

		if (stats->received_objects == stats->total_objects) {
			godot::UtilityFunctions::print("Resolving deltas ", uint32_t(stats->indexed_deltas), "/", uint32_t(stats->total_deltas));
		} else if (stats->total_objects > 0) {
			godot::UtilityFunctions::print(
					"Received ", uint32_t(stats->received_objects), "/", uint32_t(stats->total_objects),
					" objects (", uint32_t(stats->indexed_objects), ") in ", uint32_t(stats->received_bytes), " bytes");
		}
		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int fetchhead_foreach_cb(const char *ref_name, const char *remote_url, const git_oid *oid, unsigned int is_merge, void *payload) {
	try {
		(void)ref_name;
		(void)remote_url;
		if (is_merge) {
			git_oid_cpy((git_oid *)payload, oid);
		}
		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int mergehead_foreach_cb(const git_oid *oid, void *payload) {
	try {
		std::vector<git_oid> *merge_heads = static_cast<std::vector<git_oid> *>(payload);
		merge_heads->push_back(*oid);
		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int push_transfer_progress_cb(unsigned int current, unsigned int total, size_t bytes, void *payload) {
	try {
		(void)payload;
		int64_t progress = 100;

		if (total != 0) {
			progress = (current * 100) / total;
		}

		godot::UtilityFunctions::print("Writing Objects: ", uint32_t(progress), "% (", uint32_t(current), "/", uint32_t(total), ", ", uint32_t(bytes), " bytes done.)");
		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int push_update_reference_cb(const char *refname, const char *status, void *data) {
	try {
		const Credentials *credentials = static_cast<RemoteOperation *>(data)->credentials;
		const godot::String safe_refname = sanitize_git_output(godot::String::utf8(refname), credentials);
		if (status != NULL) {
			godot::String status_str = sanitize_git_output(godot::String::utf8(status), credentials);
			static_cast<RemoteOperation *>(data)->push_rejected = true;
			godot::UtilityFunctions::push_error("GitPlugin: Push rejected: ", safe_refname, " ", status_str);
		} else {
			godot::UtilityFunctions::print("[updated] ", safe_refname);
		}
		return 0;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int credentials_cb(git_cred **out, const char *url, const char *username_from_url, unsigned int allowed_types, void *payload) {
	try {
		RemoteOperation *operation = static_cast<RemoteOperation *>(payload);
		*out = nullptr;
		if (url == nullptr || operation->origin.host.empty() || git_url_contains_credentials(godot::String::utf8(url)) || !credential_origin(godot::String::utf8(url), &operation->origin).matches(operation->origin)) {
			git_error_set_str(GIT_ERROR_NET, "credential request origin does not match the remote");
			return GIT_EUSER;
		}
		if (operation->credential_attempts++ >= 3) {
			git_error_set_str(GIT_ERROR_NET, "credential attempt limit reached");
			return GIT_EUSER;
		}
		const Credentials *creds = operation->credentials;

		godot::String proper_username = username_from_url && username_from_url[0] != '\0' ? godot::String::utf8(username_from_url) : creds->username;

		if (!creds->ssh_public_key_path.is_empty()) {
			if ((allowed_types & GIT_CREDENTIAL_SSH_KEY) && !operation->key_attempted) {
				operation->key_attempted = true;
				return git_credential_ssh_key_new(out,
						CString(proper_username).data,
						CString(creds->ssh_public_key_path).data,
						CString(creds->ssh_private_key_path).data,
						CString(creds->ssh_passphrase).data);
			}
		}

		if (creds->ssh_private_key_path.is_empty() && (allowed_types & GIT_CREDENTIAL_SSH_KEY) && !proper_username.is_empty() && !operation->agent_attempted) {
			operation->agent_attempted = true;
			const int error = git_credential_ssh_key_from_agent(out, CString(proper_username).data);
			if (error == 0) {
				return 0;
			}
		}

		if ((allowed_types & GIT_CREDENTIAL_USERPASS_PLAINTEXT) && !operation->userpass_attempted) {
			operation->userpass_attempted = true;
			return git_cred_userpass_plaintext_new(out, CString(proper_username).data, CString(creds->password).data);
		}

		if ((allowed_types & GIT_CREDENTIAL_USERNAME) && !operation->username_attempted) {
			operation->username_attempted = true;
			return git_credential_username_new(out, CString(proper_username).data);
		}

		return GIT_EUSER;
	} catch (...) {
		return GIT_EUSER;
	}
}

extern "C" int diff_hunk_cb(const git_diff_delta *delta, const git_diff_hunk *range, void *payload) {
	try {
		DiffHelper *diff_helper = (DiffHelper *)payload;

		godot::Dictionary hunk = diff_helper->git_plugin->create_diff_hunk(range->old_start, range->new_start, range->old_lines, range->new_lines);
		diff_helper->diff_hunks->push_back(hunk);

		return 1;
	} catch (...) {
		return GIT_EUSER;
	}
}
