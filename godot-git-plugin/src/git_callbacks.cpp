#include <cstring>
#include <regex>
#include <string>

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
} // namespace

godot::String sanitize_git_output(const godot::String &text, const Credentials *credentials) {
	const godot::CharString encoded = text.utf8();
	std::string sanitized(encoded.get_data(), encoded.length());

	static const std::regex url_userinfo(R"(([A-Za-z][A-Za-z0-9+.-]*://)[^/@\s]+@)");
	static const std::regex scp_userinfo(R"((^|[\s'\"])([^/@\s]+)@([^/\s:]+):)");
	static const std::regex query_secret(R"(([?&](?:access_token|token|password|passwd|key|auth)=)[^&#\s]+)", std::regex::icase);
	sanitized = std::regex_replace(sanitized, url_userinfo, "$1[redacted]@");
	sanitized = std::regex_replace(sanitized, scp_userinfo, "$1[redacted]@$3:");
	sanitized = std::regex_replace(sanitized, query_secret, "$1[redacted]");

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
	const std::string value(encoded.get_data(), encoded.length());
	static const std::regex url_userinfo(R"([A-Za-z][A-Za-z0-9+.-]*://[^/@\s]+@)");
	static const std::regex scp_userinfo(R"((^|[\s'\"])[^/@\s]+@[^/\s:]+:)");
	static const std::regex query_secret(R"([?&](?:access_token|token|password|passwd|key|auth)=)", std::regex::icase);
	return std::regex_search(value, url_userinfo) || std::regex_search(value, scp_userinfo) || std::regex_search(value, query_secret);
}

extern "C" int progress_cb(const char *str, int len, void *data) {
	const Credentials *credentials = static_cast<const Credentials *>(data);
	godot::UtilityFunctions::print("remote: ", sanitize_git_output(godot::String::utf8(str, len).strip_edges(), credentials));

	return 0;
}

extern "C" int update_cb(const char *refname, const git_oid *a, const git_oid *b, void *data) {
	constexpr int short_commit_length = 8;
	char a_str[short_commit_length + 1];
	char b_str[short_commit_length + 1];
	const Credentials *credentials = static_cast<const Credentials *>(data);
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
	git_oid *merge_oid = static_cast<git_oid *>(payload);
	if (git_oid_is_zero(merge_oid)) {
		git_oid_cpy(merge_oid, oid);
	}
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
	const Credentials *credentials = static_cast<const Credentials *>(data);
	const godot::String safe_refname = sanitize_git_output(godot::String::utf8(refname), credentials);
	if (status != NULL) {
		godot::String status_str = sanitize_git_output(godot::String::utf8(status), credentials);
		godot::UtilityFunctions::print("[rejected] ", safe_refname, " ", status_str);
	} else {
		godot::UtilityFunctions::print("[updated] ", safe_refname);
	}
	return 0;
}

extern "C" int credentials_cb(git_cred **out, const char *url, const char *username_from_url, unsigned int allowed_types, void *payload) {
	(void)url;
	Credentials *creds = (Credentials *)payload;

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
