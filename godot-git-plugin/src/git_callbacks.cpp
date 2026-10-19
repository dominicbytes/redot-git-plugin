#include <algorithm>
#include <cctype>
#include <cstring>
#include <regex>
#include <string>

#include <git2/sys/errors.h>

#include "git_callbacks.h"
#include "git_plugin.h"

#include "godot_cpp/godot.hpp"
#include "godot_cpp/variant/utility_functions.hpp"

namespace {
void redact_exact(std::string &text, const godot::String &secret) {
	if (secret.is_empty()) {
		return;
	}

	const godot::CharString encoded = secret.utf8();
	const std::string value(encoded.get_data(), encoded.length());
	size_t offset = 0;
	while ((offset = text.find(value, offset)) != std::string::npos) {
		text.replace(offset, value.length(), "[redacted]");
		offset += std::strlen("[redacted]");
	}
}
std::string percent_decode(const std::string &value) {
	std::string decoded;
	for (size_t i = 0; i < value.size(); ++i) {
		if (value[i] == '%' && i + 2 < value.size() && std::isxdigit(static_cast<unsigned char>(value[i + 1])) && std::isxdigit(static_cast<unsigned char>(value[i + 2]))) {
			decoded += static_cast<char>(std::stoi(value.substr(i + 1, 2), nullptr, 16));
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

bool redact_query(std::string &value) {
	static const std::regex query(R"(([?&])([^?&=\s#]+)=([^&#\s]*))");
	std::string redacted;
	size_t offset = 0;
	bool found = false;
	for (std::sregex_iterator it(value.begin(), value.end(), query), end; it != end; ++it) {
		const std::smatch &match = *it;
		if (secret_query_name(match[2].str())) {
			redacted.append(value, offset, match.position() - offset);
			redacted += match[1].str() + match[2].str() + "=[redacted]";
			offset = match.position() + match.length();
			found = true;
		}
	}
	if (found) {
		redacted.append(value, offset, std::string::npos);
		value = redacted;
	}
	return found;
}

// Only network origins can receive credentials. Paths and malformed URLs fail closed.
godot::String credential_origin(const godot::String &url) {
	const godot::CharString encoded = url.utf8();
	const std::string value(encoded.get_data(), encoded.length());
	static const std::regex uri(R"(^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#\s]+))");
	static const std::regex scp(R"(^(?:[^/@:\s]+@)?(\[[^\]]+\]|[^/@:\s]+):[^\s]+$)");
	std::smatch match;
	std::string scheme, authority;
	if (std::regex_search(value, match, uri)) {
		scheme = lowercase(match[1].str());
		authority = match[2].str();
	} else if (std::regex_match(value, match, scp)) {
		scheme = "ssh";
		authority = match[1].str();
	} else {
		return godot::String();
	}
	if (scheme != "http" && scheme != "https" && scheme != "ssh") {
		return godot::String();
	}
	const size_t at = authority.rfind('@');
	if (at != std::string::npos) {
		authority.erase(0, at + 1);
	}
	static const std::regex host_port(R"(^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9._-]+)(?::([0-9]+))?$)");
	if (!std::regex_match(authority, match, host_port)) {
		return godot::String();
	}
	const std::string host = lowercase(match[1].str());
	std::string port = match[2].str();
	if (port.empty()) {
		port = scheme == "https" ? "443" : (scheme == "http" ? "80" : "22");
	} else {
		const size_t first = port.find_first_not_of('0');
		port = first == std::string::npos ? "0" : port.substr(first);
	}
	return godot::String::utf8((scheme + "://" + host + ":" + port).c_str());
}
} // namespace

godot::String sanitize_git_output(const godot::String &text, const Credentials *credentials) {
	const godot::CharString encoded = text.utf8();
	std::string sanitized(encoded.get_data(), encoded.length());

	static const std::regex url_userinfo(R"(([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@)");
	static const std::regex scp_userinfo(R"((^|[\s'\"])([^/@\s]+)@([^/\s:]+):)");
	sanitized = std::regex_replace(sanitized, url_userinfo, "$1[redacted]@");
	sanitized = std::regex_replace(sanitized, scp_userinfo, "$1[redacted]@$3:");
	redact_query(sanitized);

	if (credentials != nullptr) {
		redact_exact(sanitized, credentials->username);
		redact_exact(sanitized, credentials->password);
		redact_exact(sanitized, credentials->ssh_passphrase);
		redact_exact(sanitized, credentials->ssh_public_key_path);
		redact_exact(sanitized, credentials->ssh_private_key_path);
	}

	return godot::String::utf8(sanitized.c_str(), sanitized.length());
}

bool git_url_contains_credentials(const godot::String &url) {
	const godot::CharString encoded = url.utf8();
	std::string value(encoded.get_data(), encoded.length());
	if (redact_query(value)) {
		return true;
	}
	static const std::regex uri(R"(^([A-Za-z][A-Za-z0-9+.-]*)://([^/?#\s]*))");
	std::smatch match;
	if (std::regex_search(value, match, uri)) {
		const std::string authority = match[2].str();
		const size_t at = authority.rfind('@');
		if (at == std::string::npos) {
			return false;
		}
		// A username alone is conventional for SSH; all other userinfo is refused.
		return lowercase(match[1].str()) != "ssh" || percent_decode(authority.substr(0, at)).find_first_of(":@") != std::string::npos;
	}
	const size_t at = value.find('@');
	const size_t colon = value.find(':');
	if (at != std::string::npos && colon != std::string::npos) {
		return colon < at || percent_decode(value.substr(0, at)).find_first_of(":@") != std::string::npos;
	}
	return false;
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
	if (progress_overflow) {
		godot::UtilityFunctions::print("remote: [overlong progress line omitted]");
	} else if (!progress_line.empty()) {
		godot::UtilityFunctions::print("remote: ", sanitize_git_output(godot::String::utf8(progress_line.data(), progress_line.size()).strip_edges(), credentials));
	}
	progress_line.clear();
	progress_overflow = false;
}

extern "C" int progress_cb(const char *str, int len, void *data) {
	RemoteOperation *operation = static_cast<RemoteOperation *>(data);
	for (int i = 0; i < len; ++i) {
		if (str[i] == '\n') {
			operation->flush_progress();
		} else if (!operation->progress_overflow) {
			if (operation->progress_line.size() == 65536) {
				operation->progress_line.clear();
				operation->progress_overflow = true;
			} else {
				operation->progress_line += str[i];
			}
		}
	}
	return 0;
}

extern "C" int update_cb(const char *refname, const git_oid *a, const git_oid *b, void *data) {
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
}

extern "C" int transfer_progress_cb(const git_indexer_progress *stats, void *payload) {
	(void)payload;

	if (stats->received_objects == stats->total_objects) {
		godot::UtilityFunctions::print("Resolving deltas ", uint32_t(stats->indexed_deltas), "/", uint32_t(stats->total_deltas));
	} else if (stats->total_objects > 0) {
		godot::UtilityFunctions::print(
				"Received ", uint32_t(stats->received_objects), "/", uint32_t(stats->total_objects),
				" objects (", uint32_t(stats->indexed_objects), ") in ", uint32_t(stats->received_bytes), " bytes");
	}
	return 0;
}

extern "C" int fetchhead_foreach_cb(const char *ref_name, const char *remote_url, const git_oid *oid, unsigned int is_merge, void *payload) {
	(void)ref_name;
	(void)remote_url;
	if (is_merge) {
		git_oid_cpy((git_oid *)payload, oid);
	}
	return 0;
}

extern "C" int mergehead_foreach_cb(const git_oid *oid, void *payload) {
	std::vector<git_oid> *merge_heads = static_cast<std::vector<git_oid> *>(payload);
	merge_heads->push_back(*oid);
	return 0;
}

extern "C" int push_transfer_progress_cb(unsigned int current, unsigned int total, size_t bytes, void *payload) {
	(void)payload;
	int64_t progress = 100;

	if (total != 0) {
		progress = (current * 100) / total;
	}

	godot::UtilityFunctions::print("Writing Objects: ", uint32_t(progress), "% (", uint32_t(current), "/", uint32_t(total), ", ", uint32_t(bytes), " bytes done.)");
	return 0;
}

extern "C" int push_update_reference_cb(const char *refname, const char *status, void *data) {
	const Credentials *credentials = static_cast<RemoteOperation *>(data)->credentials;
	const godot::String safe_refname = sanitize_git_output(godot::String::utf8(refname), credentials);
	if (status != NULL) {
		godot::String status_str = sanitize_git_output(godot::String::utf8(status), credentials);
		static_cast<RemoteOperation *>(data)->push_rejected = true;
		godot::UtilityFunctions::push_error("GitPlugin: Push rejected: ", safe_refname, " ", status_str);
		git_error_set_str(GIT_ERROR_NET, "remote rejected a reference update");
		return GIT_EUSER;
	} else {
		godot::UtilityFunctions::print("[updated] ", safe_refname);
	}
	return 0;
}

extern "C" int credentials_cb(git_cred **out, const char *url, const char *username_from_url, unsigned int allowed_types, void *payload) {
	RemoteOperation *operation = static_cast<RemoteOperation *>(payload);
	*out = nullptr;
	if (url == nullptr || operation->origin.is_empty() || git_url_contains_credentials(godot::String::utf8(url)) || credential_origin(godot::String::utf8(url)) != operation->origin) {
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
		if (allowed_types & GIT_CREDENTIAL_SSH_KEY) {
			return git_credential_ssh_key_new(out,
					CString(proper_username).data,
					CString(creds->ssh_public_key_path).data,
					CString(creds->ssh_private_key_path).data,
					CString(creds->ssh_passphrase).data);
		}
	}

	if (creds->ssh_private_key_path.is_empty() && (allowed_types & GIT_CREDENTIAL_SSH_KEY) && !proper_username.is_empty()) {
		if (operation->agent_attempted) {
			git_error_set_str(GIT_ERROR_SSH, "SSH agent authentication already attempted");
			return GIT_EUSER;
		}
		operation->agent_attempted = true;
		return git_credential_ssh_key_from_agent(out, CString(proper_username).data);
	}

	if (allowed_types & GIT_CREDENTIAL_USERPASS_PLAINTEXT) {
		return git_cred_userpass_plaintext_new(out, CString(proper_username).data, CString(creds->password).data);
	}

	if (allowed_types & GIT_CREDENTIAL_USERNAME) {
		return git_credential_username_new(out, CString(proper_username).data);
	}

	return GIT_EUSER;
}

extern "C" int diff_hunk_cb(const git_diff_delta *delta, const git_diff_hunk *range, void *payload) {
	DiffHelper *diff_helper = (DiffHelper *)payload;

	godot::Dictionary hunk = diff_helper->git_plugin->create_diff_hunk(range->old_start, range->new_start, range->old_lines, range->new_lines);
	diff_helper->diff_hunks->push_back(hunk);

	return 1;
}
