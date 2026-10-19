#pragma once

#include <unordered_map>

#include "git_callbacks.h"
#include "git_wrappers.h"

#include "godot_cpp/classes/editor_vcs_interface.hpp"
#include "git2.h"

#include <vector>

struct Credentials {
	godot::String username;
	godot::String password;
	godot::String ssh_public_key_path;
	godot::String ssh_private_key_path;
	godot::String ssh_passphrase;

	void clear() {
		username = godot::String();
		password = godot::String();
		ssh_public_key_path = godot::String();
		ssh_private_key_path = godot::String();
		ssh_passphrase = godot::String();
	}
};

class GitPlugin : public godot::EditorVCSInterface {
	GDCLASS(GitPlugin, godot::EditorVCSInterface);

protected:
	static void _bind_methods();

public:
	Credentials creds;
	bool has_merge = false;
	bool libgit2_initialized = false;
	git_repository_ptr repo;
	git_oid pull_merge_oid = {};
	godot::String repo_project_path;
	std::unordered_map<git_status_t, ChangeType> map_changes;

	GitPlugin();

	// Endpoints
	bool _initialize(const godot::String &project_path) override;
	void _set_credentials(const godot::String &username, const godot::String &password, const godot::String &ssh_public_key_path, const godot::String &ssh_private_key_path, const godot::String &ssh_passphrase) override;
	godot::TypedArray<godot::Dictionary> _get_modified_files_data() override;
	void _stage_file(const godot::String &file_path) override;
	void _unstage_file(const godot::String &file_path) override;
	void _discard_file(const godot::String &file_path) override;
	void _commit(const godot::String &msg) override;
	godot::TypedArray<godot::Dictionary> _get_diff(const godot::String &identifier, int32_t area) override;
	bool _shut_down() override;
	godot::String _get_vcs_name() override;
	godot::TypedArray<godot::Dictionary> _get_previous_commits(int32_t max_commits) override;
	godot::TypedArray<godot::String> _get_branch_list() override;
	godot::TypedArray<godot::String> _get_remotes() override;
	void _create_branch(const godot::String &branch_name) override;
	void _remove_branch(const godot::String &branch_name) override;
	void _create_remote(const godot::String &remote_name, const godot::String &remote_url) override;
	void _remove_remote(const godot::String &remote_name) override;
	godot::String _get_current_branch_name() override;
	bool _checkout_branch(const godot::String &branch_name) override;
	void _pull(const godot::String &remote) override;
	void _push(const godot::String &remote, bool force) override;
	void _fetch(const godot::String &remote) override;
	godot::TypedArray<godot::Dictionary> _get_line_diff(const godot::String &file_path, const godot::String &text) override;

	// Helpers
	godot::TypedArray<godot::Dictionary> _parse_diff(git_diff *p_diff);
	bool validate_remote_url(const git_remote *remote, git_direction direction);
	bool check_errors(int error, godot::String function, godot::String file, int line, godot::String message, const std::vector<git_error_code> &ignores = {});
#ifdef REDOT_GIT_TEST_HARNESS
	godot::String test_sanitize_output(const godot::String &text);
	bool test_remote_url_allowed(const godot::String &remote, bool push);
	godot::Array test_credential_requests(const godot::String &origin, const godot::Array &urls, int types, const godot::String &username);
	void test_progress_packets(const godot::Array &packets);
	bool test_push_rejection(const godot::String &status);
	bool test_credentials_empty() const;
	bool test_set_ca_certificate(const godot::String &path);
#endif
};
