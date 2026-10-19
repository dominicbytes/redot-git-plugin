extends SceneTree

const RESULT_PREFIX := "REDOT_GIT_PROVIDER_TEST="
const TREE_AREA_STAGED := 1
const TREE_AREA_UNSTAGED := 2

var _providers: Array[Object] = []


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	for _frame: int in range(300):
		if ClassDB.class_exists(&"GitPlugin"):
			break
		await process_frame

	var arguments := OS.get_cmdline_user_args()
	var scenario := arguments[0] if not arguments.is_empty() else "local"
	var result: Dictionary
	match scenario:
		"nonrepo":
			result = _run_non_repository()
		"unborn":
			result = _run_unborn()
		"remote":
			result = _run_remote()
		"reject":
			result = _run_push(false)
		"force":
			result = _run_push(true)
		"merge":
			result = _run_merge()
		"conflict":
			result = _run_conflict()
		"resolve":
			result = _run_resolution()
		"security":
			result = _run_security()
		"security_authority", "security_uri_output", "security_ambiguous_query", "security_ambiguous_fragment", "security_urls", "security_origins", "security_overlap", "security_long_output", "security_cr", "security_fallback", "security_redirect_cross", "security_redirect_same":
			result = _run_security_regression(scenario)
		"edge":
			result = _run_edge_matrix()
		"detached":
			result = _run_detached()
		"case_unstage_old_first", "case_unstage_new_first", "missing_index_stage", "missing_index_unstage", "missing_index_commit", "directory_to_file_unstage", "file_to_directory_stage", "gitlink_stage":
			result = _run_index_regression(scenario)
		"literal_stage", "literal_unstage", "literal_discard", "external_stage", "external_unstage", "external_commit", "rename_commit", "staged_path", "branch_collision", "merge_external", "merge_aborted", "merge_resumed", "merge_octopus", "pending_pull", "legacy_encoding", "unborn_line":
			result = _run_local_regression(scenario)
		_:
			result = _run_local()
	var freed := true
	for provider: Object in _providers:
		provider.call("test_shutdown")
		var instance_id := provider.get_instance_id()
		provider.free()
		freed = freed and not is_instance_id_valid(instance_id)
	result["providers_freed"] = freed
	result["passed"] = result.get("passed", false) and result.providers_freed
	_providers.clear()
	print(RESULT_PREFIX + JSON.stringify(result))
	if not result.get("passed", false):
		quit(1)


func _new_provider() -> Object:
	if not ClassDB.class_exists(&"GitPlugin") or not ClassDB.can_instantiate(&"GitPlugin"):
		return null
	var provider: Object = ClassDB.instantiate(&"GitPlugin")
	_providers.append(provider)
	return provider


func _run_non_repository() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "nonrepo", "passed": false, "reason": "GitPlugin was not instantiable"}
	var initialized: bool = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	return {
		"scenario": "nonrepo",
		"initialized": initialized,
		"passed": not initialized,
	}


func _run_local() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "local", "passed": false, "reason": "GitPlugin was not instantiable"}

	var result: Dictionary = {"scenario": "local"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	if not result.initialize:
		result["passed"] = false
		return result

	result["vcs_name"] = provider.call("test_get_vcs_name")
	result["branch_before"] = provider.call("test_get_current_branch_name")
	result["status_before"] = provider.call("test_get_modified_files_data")
	result["unstaged_diff"] = provider.call("test_get_diff", "tracked.txt", TREE_AREA_UNSTAGED)
	result["unicode_line_diff"] = provider.call("test_get_line_diff", "unicode.txt", "café\nééééé\none\ntwo\n")

	provider.call("test_discard_file", "discard.txt")
	result["discarded_text"] = FileAccess.get_file_as_string("res://discard.txt")

	provider.call("test_stage_file", "unstage.txt")
	result["status_staged"] = provider.call("test_get_modified_files_data")
	provider.call("test_unstage_file", "unstage.txt")
	result["status_unstaged"] = provider.call("test_get_modified_files_data")

	provider.call("test_stage_file", "untracked.txt")
	provider.call("test_commit", "Provider fixture commit")
	result["history_one"] = provider.call("test_get_previous_commits", 1)
	result["history_zero"] = provider.call("test_get_previous_commits", 0)

	provider.call("test_create_branch", "provider-feature")
	result["branches_created"] = provider.call("test_get_branch_list")
	result["checkout_feature"] = provider.call("test_checkout_branch", "provider-feature")
	result["branch_feature"] = provider.call("test_get_current_branch_name")
	result["checkout_main"] = provider.call("test_checkout_branch", "main")
	provider.call("test_remove_branch", "provider-feature")
	result["branches_removed"] = provider.call("test_get_branch_list")

	provider.call("test_create_remote", "fixture", ProjectSettings.globalize_path("res://../remote.git"))
	result["remotes_created"] = provider.call("test_get_remotes")
	provider.call("test_remove_remote", "fixture")
	result["remotes_removed"] = provider.call("test_get_remotes")

	provider.call("test_set_credentials", "fixture-user", "fixture-secret", "", "", "")
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = _local_passed(result)
	return result


func _run_unborn() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "unborn", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "unborn"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	result["branch_before"] = provider.call("test_get_current_branch_name")
	_write_file("res://initial.txt", "initial content\n")
	provider.call("test_stage_file", "initial.txt")
	result["status_staged"] = provider.call("test_get_modified_files_data")
	provider.call("test_unstage_file", "initial.txt")
	result["status_unstaged"] = provider.call("test_get_modified_files_data")
	provider.call("test_stage_file", "initial.txt")
	provider.call("test_commit", "Initial provider commit")
	result["branch_after"] = provider.call("test_get_current_branch_name")
	result["history"] = provider.call("test_get_previous_commits", 2)
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = (
		result.initialize
		and result.branch_before == ""
		and _has_status(result.status_staged, "initial.txt", TREE_AREA_STAGED)
		and _has_status(result.status_unstaged, "initial.txt", TREE_AREA_UNSTAGED)
		and result.branch_after == "main"
		and result.history.size() == 1
		and result.shutdown
	)
	return result


func _run_remote() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "remote", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "remote"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	provider.call("test_fetch", "origin")
	provider.call("test_pull", "origin")
	result["pulled_text"] = FileAccess.get_file_as_string("res://upstream.txt")
	provider.call("test_pull", "origin")
	_write_file("res://provider-push.txt", "pushed by provider\n")
	provider.call("test_stage_file", "provider-push.txt")
	provider.call("test_commit", "Provider remote commit")
	result["local_tip"] = provider.call("test_get_previous_commits", 1)
	provider.call("test_push", "origin", false)
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = (
		result.initialize
		and result.pulled_text.replace("\r\n", "\n") == "from upstream\n"
		and result.local_tip.size() == 1
		and result.shutdown
	)
	return result


func _run_push(force: bool) -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "force" if force else "reject", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "force" if force else "reject", "force": force}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	result["local_tip"] = provider.call("test_get_previous_commits", 1)
	provider.call("test_push", "origin", force)
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = result.initialize and result.local_tip.size() == 1 and result.shutdown
	return result


func _run_merge() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "merge", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "merge"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	provider.call("test_pull", "origin")
	result["status_after_pull"] = provider.call("test_get_modified_files_data")
	provider.call("test_commit", "Provider merge commit")
	result["history"] = provider.call("test_get_previous_commits", 1)
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = result.initialize and result.history.size() == 1 and result.shutdown
	return result


func _run_conflict() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "conflict", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "conflict"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	provider.call("test_pull", "origin")
	result["status"] = provider.call("test_get_modified_files_data")
	result["has_conflict"] = _has_change_type(result.status, 5)
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = result.initialize and result.has_conflict and result.shutdown
	return result


func _run_resolution() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "resolve", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "resolve"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	_write_file("res://conflict.txt", "resolved by provider\n")
	provider.call("test_stage_file", "conflict.txt")
	provider.call("test_commit", "Resolve provider conflict")
	result["history"] = provider.call("test_get_previous_commits", 1)
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = result.initialize and result.history.size() == 1 and result.shutdown
	return result


func _run_security() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "security", "passed": false, "reason": "GitPlugin was not instantiable"}
	var password := "SENTINEL_" + "PASSWORD_42"
	var passphrase := "SENTINEL_" + "PASSPHRASE_42"
	var public_key := "sentinel/" + "PUBLIC_KEY_42.pub"
	var private_key := "sentinel/" + "PRIVATE_KEY_42"
	var username := "sentinel-" + "user-42"
	var url_secret := "SENTINEL_" + "URL_SECRET_42"
	var query_secret := "SENTINEL_" + "QUERY_SECRET_42"
	var result: Dictionary = {"scenario": "security"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	provider.call("test_set_credentials", username, password, public_key, private_key, passphrase)
	var sensitive_text := "https://" + username + ":" + password + "@example.invalid/repo?token=" + query_secret + " " + public_key + " " + private_key + " " + passphrase
	result["sanitized"] = provider.call("test_sanitize_output", sensitive_text)
	var rejected_urls: Array[String] = [
		"https://user@example.invalid/repo",
		"https://user:" + url_secret + "@example.invalid/repo",
		"ssh://user:" + url_secret + "@example.invalid/repo",
		"ssh://user:@example.invalid/repo",
		"user:" + url_secret + "@example.invalid:repo.git",
	]
	for query_name: String in ["%74oken", "api_key", "client_secret", "APIKEY", "private_token", "sig", "signature", "access_token", "key", "password", "passwd", "pass", "secret", "auth"]:
		rejected_urls.append("https://example.invalid/repo?" + query_name + "=" + query_secret)
		var sanitized: String = provider.call("test_sanitize_output", "https://example.invalid/repo?" + query_name + "=" + query_secret)
		result["sanitized"] += " " + sanitized
	for index: int in range(rejected_urls.size()):
		provider.call("test_create_remote", "blocked-" + str(index), rejected_urls[index])
	provider.call("test_create_remote", "scp-username", "git@example.invalid:owner/repo.git")
	provider.call("test_create_remote", "ssh-username", "ssh://git@example.invalid/owner/repo.git")
	result["remotes"] = provider.call("test_get_remotes")
	var urls_rejected := true
	for index: int in range(rejected_urls.size()):
		urls_rejected = urls_rejected and not result.remotes.has("blocked-" + str(index))
	result["url_policy"] = urls_rejected and result.remotes.has("scp-username") and result.remotes.has("ssh-username")
	result["callback_policy"] = false
	result["effective_urls"] = false
	result["push_rejection"] = false
	if provider.has_method("test_credential_requests"):
		result["effective_urls"] = _security_effective_urls(provider)
		result["callback_policy"] = _security_credentials(provider, username, password)
		provider.call("test_set_credentials", username, password, public_key, private_key, passphrase)
		var packets: Array[String] = []
		for index: int in range(sensitive_text.length()):
			packets.append(sensitive_text.substr(index, 1))
		packets.append("\n")
		# The final unterminated line is flushed by the operation destructor.
		packets.append("https://user:UNCONFIGURED_" + "SPLIT_SECRET_42@example.invalid/repo?%74oken=")
		packets.append("UNCONFIGURED_" + "QUERY_SECRET_42")
		provider.call("test_progress_packets", packets)
		result["push_rejection"] = provider.call("test_push_rejection", "hook declined " + sensitive_text)
	# Exercise real local push status failures as well as the callback directly.
	provider.call("test_push", "locked-remote", false)
	# Remote names and libgit2 errors must use the same sanitizer.
	provider.call("test_fetch", password)
	provider.call("test_pull", passphrase)
	provider.call("test_push", private_key, false)
	result["shutdown"] = provider.call("test_shutdown")
	result["credentials_empty"] = provider.call("test_credentials_empty")
	result["passed"] = (
		result.initialize
		and result.url_policy
		and result.callback_policy
		and result.effective_urls
		and result.push_rejection
		and result.sanitized.contains("[redacted]")
		and not result.sanitized.contains("SENTINEL_")
		and result.shutdown
		and result.credentials_empty
	)
	return result


func _security_effective_urls(provider: Object) -> bool:
	var passed := true
	for remote: String in ["unsafe-fetch", "rewritten-fetch", "rewritten-push", "unsafe-push"]:
		var push := remote.ends_with("push")
		var allowed: bool = provider.call("test_remote_url_allowed", remote, push)
		passed = passed and not allowed
		if push:
			# Safe fetch URL is unaffected by an unsafe push URL.
			passed = passed and provider.call("test_remote_url_allowed", remote, false)
			provider.call("test_push", remote, false)
		else:
			provider.call("test_fetch", remote)
			provider.call("test_pull", remote)
	provider.call("test_create_remote", "rewritten-create", "fixture-fetch:other.git")
	var remotes: Array = provider.call("test_get_remotes")
	return passed and not remotes.has("rewritten-create")


func _security_credentials(provider: Object, username: String, password: String) -> bool:
	provider.call("test_set_credentials", username, password, "", "", "")
	var origin := "https://example.invalid/repo"
	var same := "https://EXAMPLE.invalid:443/other"
	var attempts: Array = provider.call("test_credential_requests", origin, [same, same, same, same, same], 1, "")
	var origins: Array = provider.call("test_credential_requests", origin, ["https://other.invalid/repo", "http://example.invalid/repo", "https://example.invalid:444/repo", "file:///repo", "invalid"], 1, "")
	var agent: Array = provider.call("test_credential_requests", "git@example.invalid:owner/repo.git", ["ssh://git@example.invalid:22/repo", "ssh://git@example.invalid/repo"], 2, "git")
	var ssh_username: Array = provider.call("test_credential_requests", "ssh://git@example.invalid/repo", ["git@example.invalid:owner/repo.git"], 32, "git")
	var fresh: Array = provider.call("test_credential_requests", origin, [same], 1, "")
	return attempts == [true, false, false, false, false] and origins == [false, false, false, false, false] and agent == [true, false] and ssh_username == [true] and fresh == [true]


func _run_edge_matrix() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "edge", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "edge"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	var status: Array = provider.call("test_get_modified_files_data")
	result["status"] = status
	var history_before: Array = provider.call("test_get_previous_commits", 10)
	result["history_before"] = history_before
	var root_id: String = history_before[history_before.size() - 1].get("id", "")
	var latest_id: String = history_before[0].get("id", "")
	result["root_diff_count"] = provider.call("test_get_diff", root_id, 0).size()
	result["latest_diff_count"] = provider.call("test_get_diff", latest_id, 0).size()
	result["modified_diff_count"] = provider.call("test_get_diff", "modified.txt", TREE_AREA_UNSTAGED).size()
	result["staged_diff_count"] = provider.call("test_get_diff", "staged-new.txt", TREE_AREA_STAGED).size()
	var large_diff: Array = provider.call("test_get_diff", "large.txt", TREE_AREA_UNSTAGED)
	result["large_diff_count"] = large_diff.size()
	result["large_diff_complete"] = _large_diff_complete(large_diff)
	result["binary_diff_count"] = provider.call("test_get_diff", "binary.bin", TREE_AREA_UNSTAGED).size()

	provider.call("test_stage_file", "unicodé file.txt")
	provider.call("test_commit", "Provider café\nsecond line")
	result["history_after"] = provider.call("test_get_previous_commits", 1)

	provider.call("test_create_branch", "feature-é")
	result["branches_unicode"] = provider.call("test_get_branch_list")
	result["checkout_unicode"] = provider.call("test_checkout_branch", "feature-é")
	result["branch_unicode"] = provider.call("test_get_current_branch_name")
	result["checkout_main"] = provider.call("test_checkout_branch", "main")
	provider.call("test_remove_branch", "feature-é")
	provider.call("test_create_branch", "invalid branch")
	provider.call("test_remove_branch", "main")
	result["branches_final"] = provider.call("test_get_branch_list")
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = (
		result.initialize
		and _has_status(status, "modified.txt", TREE_AREA_UNSTAGED)
		and _has_change(status, "deleted.txt", 3, TREE_AREA_UNSTAGED)
		and _has_change(status, "renamed.txt", 0, TREE_AREA_UNSTAGED)
		and _has_change(status, "rename-old.txt", 3, TREE_AREA_UNSTAGED)
		and _has_change(status, "staged-rename-old.txt", 3, TREE_AREA_STAGED)
		and _has_change(status, "staged-renamed.txt", 0, TREE_AREA_STAGED)
		and _has_status(status, "staged-new.txt", TREE_AREA_STAGED)
		and _has_status(status, "unicodé file.txt", TREE_AREA_UNSTAGED)
		and result.root_diff_count > 0
		and result.latest_diff_count > 0
		and result.modified_diff_count > 0
		and result.staged_diff_count > 0
		and result.large_diff_count > 0
		and result.large_diff_complete
		and result.binary_diff_count > 0
		and result.history_after.size() == 1
		and result.history_after[0].get("message", "") == "Provider café\nsecond line"
		and result.branches_unicode.has("feature-é")
		and result.checkout_unicode
		and result.branch_unicode == "feature-é"
		and result.checkout_main
		and not result.branches_final.has("feature-é")
		and not result.branches_final.has("invalid branch")
		and result.branches_final.has("main")
		and result.shutdown
	)
	return result


func _run_detached() -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": "detached", "passed": false, "reason": "GitPlugin was not instantiable"}
	var result: Dictionary = {"scenario": "detached"}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	result["branch"] = provider.call("test_get_current_branch_name")
	result["branches"] = provider.call("test_get_branch_list")
	result["checkout_main"] = provider.call("test_checkout_branch", "main")
	result["branch_after"] = provider.call("test_get_current_branch_name")
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = (
		result.initialize
		and result.branch == ""
		and result.branches.has("main")
		and result.checkout_main
		and result.branch_after == "main"
		and result.shutdown
	)
	return result


func _write_file(path: String, contents: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(contents)
	file.close()


func _has_status(items: Array, file_path: String, area: int) -> bool:
	for item: Dictionary in items:
		if item.get("file_path") == file_path and item.get("area") == area:
			return true
	return false


func _has_change_type(items: Array, change_type: int) -> bool:
	for item: Dictionary in items:
		if item.get("change_type") == change_type:
			return true
	return false


func _has_change(items: Array, file_path: String, change_type: int, area: int) -> bool:
	for item: Dictionary in items:
		if item.get("file_path") == file_path and item.get("change_type") == change_type and item.get("area") == area:
			return true
	return false


func _has_hunk_with_new_lines(items: Array, line_count: int) -> bool:
	for item: Dictionary in items:
		if item.get("new_lines") == line_count:
			return true
	return false


func _local_passed(result: Dictionary) -> bool:
	return (
		result.get("initialize") == true
		and result.get("shutdown") == true
		and result.get("vcs_name") == "Git"
		and result.get("branch_before") == "main"
		and _has_status(result.get("status_before", []), "untracked.txt", TREE_AREA_UNSTAGED)
		and not result.get("unstaged_diff", []).is_empty()
		and _has_hunk_with_new_lines(result.get("unicode_line_diff", []), 3)
		and result.get("discarded_text", "").replace("\r\n", "\n") == "keep\n"
		and _has_status(result.get("status_staged", []), "unstage.txt", TREE_AREA_STAGED)
		and _has_status(result.get("status_unstaged", []), "unstage.txt", TREE_AREA_UNSTAGED)
		and result.get("history_one", []).size() == 1
		and result.get("history_zero", []).is_empty()
		and result.get("branches_created", []).has("provider-feature")
		and result.get("checkout_feature") == true
		and result.get("branch_feature") == "provider-feature"
		and result.get("checkout_main") == true
		and not result.get("branches_removed", []).has("provider-feature")
		and result.get("remotes_created", []).has("fixture")
		and not result.get("remotes_removed", []).has("fixture")
	)


func _git(arguments: PackedStringArray) -> Dictionary:
	var output: Array = []
	var command := PackedStringArray(["-C", ProjectSettings.globalize_path("res://")])
	command.append_array(arguments)
	var code := OS.execute("git", command, output, true)
	return {"code": code, "text": "".join(output).strip_edges()}


func _large_diff_complete(files: Array) -> bool:
	var added := 0
	var last := false
	for file: Dictionary in files:
		for hunk: Dictionary in file.get("diff_hunks", []):
			for line: Dictionary in hunk.get("diff_lines", []):
				if line.get("status") == "+":
					added += 1
					last = last or line.get("new_line_no") == 20000
	return added >= 10000 and last


func _run_index_regression(scenario: String) -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": scenario, "passed": false}
	var result: Dictionary = {"scenario": scenario}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	if not result.initialize:
		result["passed"] = false
		return result
	var status: Array = provider.call("test_get_modified_files_data")
	var ok := true
	match scenario:
		"case_unstage_old_first", "case_unstage_new_first":
			var paths: Array[String] = []
			for row: Dictionary in status:
				if row.get("area") == TREE_AREA_STAGED:
					paths.append(row.file_path)
			paths.sort()
			ok = paths == ["Name.txt", "name.txt"]
			if scenario == "case_unstage_new_first":
				paths.reverse()
			for path: String in paths:
				provider.call("test_unstage_file", path)
			result["unstage_order"] = paths
		"missing_index_stage", "missing_index_unstage", "missing_index_commit":
			ok = DirAccess.remove_absolute(ProjectSettings.globalize_path("res://.git/index")) == OK
			result["index_deleted"] = ok
			if scenario == "missing_index_stage":
				provider.call("test_stage_file", "selected.txt")
			elif scenario == "missing_index_unstage":
				provider.call("test_unstage_file", "selected.txt")
			else:
				provider.call("test_commit", "Commit externally cleared index")
		"directory_to_file_unstage":
			ok = _has_status(status, "node", TREE_AREA_STAGED) and _has_status(status, "node/child.txt", TREE_AREA_STAGED)
			provider.call("test_unstage_file", "node")
			result["intermediate_entries"] = _git(["ls-files", "--stage"]).text
			ok = ok and result.intermediate_entries.is_empty()
			provider.call("test_unstage_file", "node/child.txt")
		"file_to_directory_stage":
			ok = _has_status(status, "node", TREE_AREA_UNSTAGED)
			provider.call("test_stage_file", "node")
			ok = ok and FileAccess.get_file_as_string("res://node/child.txt") == "untracked child\n"
		"gitlink_stage":
			provider.call("test_stage_file", "node")
	result["index_entries"] = _git(["ls-files", "--stage"]).text
	result["passed"] = ok
	return result


func _run_local_regression(scenario: String) -> Dictionary:
	var provider := _new_provider()
	if provider == null:
		return {"scenario": scenario, "passed": false}
	var result: Dictionary = {"scenario": scenario}
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	if not result.initialize:
		result["passed"] = false
		return result
	var ok := true
	match scenario:
		"literal_stage":
			provider.call("test_stage_file", "asset[1].txt")
			var status: Array = provider.call("test_get_modified_files_data")
			ok = _has_status(status, "asset[1].txt", TREE_AREA_STAGED) and not _has_status(status, "asset1.txt", TREE_AREA_STAGED)
		"literal_unstage":
			provider.call("test_unstage_file", "asset[1].txt")
			var status: Array = provider.call("test_get_modified_files_data")
			ok = not _has_status(status, "asset[1].txt", TREE_AREA_STAGED) and _has_status(status, "asset1.txt", TREE_AREA_STAGED)
		"literal_discard":
			provider.call("test_discard_file", "asset[1].txt")
			ok = FileAccess.get_file_as_string("res://asset[1].txt").strip_edges() == "base" and FileAccess.get_file_as_string("res://asset1.txt").strip_edges() == "changed"
		"external_stage", "external_unstage", "external_commit":
			provider.call("test_get_modified_files_data")
			ok = _git(["add", "external.txt"]).code == 0
			if scenario == "external_stage":
				provider.call("test_stage_file", "selected.txt")
			elif scenario == "external_unstage":
				provider.call("test_unstage_file", "selected.txt")
			else:
				provider.call("test_commit", "Keep external staging")
			var command := PackedStringArray(["show", "HEAD:external.txt"]) if scenario == "external_commit" else PackedStringArray(["show", ":external.txt"])
			var external := _git(command)
			ok = ok and external.code == 0 and external.text == "external changed"
		"rename_commit":
			var status: Array = provider.call("test_get_modified_files_data")
			for row: Dictionary in status:
				if row.get("area") == TREE_AREA_UNSTAGED:
					provider.call("test_stage_file", row.file_path)
			provider.call("test_commit", "Commit rename")
			ok = _git(["ls-tree", "--name-only", "HEAD"]).text.split("\n") == PackedStringArray(["destination.txt"])
		"staged_path":
			var status: Array = provider.call("test_get_modified_files_data")
			ok = _has_status(status, "index.txt", TREE_AREA_STAGED) and not _has_status(status, "working.txt", TREE_AREA_STAGED)
		"branch_collision":
			ok = provider.call("test_checkout_branch", "feature")
			result["branch_content"] = FileAccess.get_file_as_string("res://branch.txt").strip_edges()
			result["head_blob"] = _git(["rev-parse", "HEAD:branch.txt"]).text
			result["index_blob"] = _git(["rev-parse", ":branch.txt"]).text
			ok = ok and result.branch_content == "feature" and result.head_blob == result.index_blob and _git(["diff-index", "--quiet", "HEAD"]).code == 0
		"merge_external", "merge_aborted", "merge_resumed", "merge_octopus":
			if scenario == "merge_external":
				ok = _git(["merge", "--no-ff", "--no-commit", "side"]).code == 0
			if scenario == "merge_aborted":
				ok = _git(["merge", "--abort"]).code == 0
			var expected: Array = [_git(["rev-parse", "HEAD"]).text]
			if scenario != "merge_aborted":
				for oid: String in FileAccess.get_file_as_string("res://.git/MERGE_HEAD").strip_edges().split("\n"):
					expected.append(oid)
			provider.call("test_commit", "Commit current repository state")
			var actual: PackedStringArray = _git(["rev-list", "--parents", "-n", "1", "HEAD"]).text.split(" ")
			actual.remove_at(0)
			ok = ok and Array(actual) == expected and not FileAccess.file_exists("res://.git/MERGE_HEAD")
		"pending_pull":
			var before := FileAccess.get_file_as_bytes("res://.git/MERGE_HEAD")
			provider.call("test_pull", "origin")
			ok = FileAccess.file_exists("res://.git/MERGE_HEAD") and FileAccess.get_file_as_bytes("res://.git/MERGE_HEAD") == before
		"legacy_encoding":
			var history: Array = provider.call("test_get_previous_commits", 10)
			var messages: Array = []
			var authors: Array = []
			for commit: Dictionary in history:
				messages.append(commit.get("message", ""))
				authors.append(commit.get("author", ""))
			result["messages"] = messages
			result["authors"] = authors
			ok = messages.has("Fallback \u00e9\n") and messages.has("Declared \u00c3\u00a9\n") and messages.has("Alias \u00c3\u00a9\n")
			ok = ok and authors.count("Jos\u00e9 <fixture@example.invalid>") == 3
			var diff: Array = provider.call("test_get_diff", "legacy.txt", TREE_AREA_UNSTAGED)
			var contents := ""
			for file: Dictionary in diff:
				for hunk: Dictionary in file.get("diff_hunks", []):
					for line: Dictionary in hunk.get("diff_lines", []):
						contents += line.get("content", "")
			result["legacy_contents"] = contents
			ok = ok and contents.contains("caf\u00e9") and contents.contains("\u00ff changed") and not contents.contains("\ufffd")
		"unborn_line":
			_write_file("res://initial.txt", "staged\n")
			provider.call("test_stage_file", "initial.txt")
			var diff: Array = provider.call("test_get_line_diff", "initial.txt", "edited\n")
			ok = not diff.is_empty()
	result["behavior_passed"] = ok
	result["shutdown"] = provider.call("test_shutdown")
	result["passed"] = ok and result.shutdown
	return result


func _run_security_regression(scenario: String) -> Dictionary:
	var provider := _new_provider()
	var result := {"scenario": scenario, "passed": false}
	if provider == null:
		return result
	result["initialize"] = provider.call("test_initialize", ProjectSettings.globalize_path("res://"))
	provider.call("test_set_credentials", "fixture", "fixture-password", "", "", "")
	var passed: bool = result.initialize
	match scenario:
		"security_redirect_cross", "security_redirect_same":
			var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://redirect-config.json"))
			provider.call("test_set_credentials", "fixture", "redirect-password", "", "", "")
			provider.call("test_create_remote", "redirect-loopback", config.url)
			provider.call("test_fetch", "redirect-loopback")
		"security_ambiguous_query", "security_ambiguous_fragment":
			var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://redirect-config.json"))
			provider.call("test_create_remote", "ambiguous-create", config.url)
			passed = not provider.call("test_get_remotes").has("ambiguous-create") and passed
			passed = not provider.call("test_remote_url_allowed", "ambiguous-effective", false) and passed
			passed = not provider.call("test_remote_url_allowed", "ambiguous-effective", true) and passed
			provider.call("test_fetch", "ambiguous-effective")
			provider.call("test_push", "ambiguous-effective", false)
		"security_authority":
			var checks: Array = []
			for delimiter: String in ["?", "#"]:
				for scheme: String in ["http", "https", "ssh"]:
					var userinfo := "user:URL_SECRET" + delimiter + "x"
					var url := scheme + "://" + userinfo + "@example.invalid/repo"
					var name := "ambiguous-" + str(checks.size())
					provider.call("test_create_remote", name, url)
					checks.append(not provider.call("test_get_remotes").has(name))
					checks.append(provider.call("test_sanitize_output", url) == scheme + "://[redacted]@example.invalid/repo")
					checks.append(provider.call("test_credential_requests", scheme + "://example.invalid/repo", [url], 1, "") == [false])
				var http_user := "https://user" + delimiter + "x@example.invalid/repo"
				provider.call("test_create_remote", "http-user-" + str(checks.size()), http_user)
				checks.append(provider.call("test_sanitize_output", http_user) == "https://[redacted]@example.invalid/repo")
				checks.append(not provider.call("test_get_remotes").has("http-user-" + str(checks.size() - 1)))
				var ssh_empty := "ssh://user" + delimiter + "x:@example.invalid/repo"
				provider.call("test_create_remote", "ssh-empty-" + str(checks.size()), ssh_empty)
				checks.append(not provider.call("test_get_remotes").has("ssh-empty-" + str(checks.size())))
				checks.append(provider.call("test_sanitize_output", ssh_empty) == "ssh://[redacted]@example.invalid/repo")
			result["checks"] = checks
			passed = not checks.has(false) and passed
		"security_uri_output":
			var cases: Array = [
				["https://a:ONE_SECRET@host/r,https://b:TWO_SECRET@host/r", "https://[redacted]@host/r,https://[redacted]@host/r"],
				["https://a:ONE_SECRET@host/r;https://b:TWO_SECRET@host/r", "https://[redacted]@host/r;https://[redacted]@host/r"],
				["https://host/r,https://b:TWO_SECRET@host/r", "https://host/r,https://[redacted]@host/r"],
				["https://host/repo?redirect=https://u:URL_SECRET@host/b", "https://host/repo?redirect=https://[redacted]@host/b"],
			]
			var checks: Array = []
			for pair: Array in cases:
				checks.append(provider.call("test_sanitize_output", pair[0]) == pair[1])
			# Many URI occurrences in one token must complete without rescanning suffixes.
			checks.append(provider.call("test_sanitize_output", "https://u:URL_SECRET@host/r,".repeat(2000)) == "https://[redacted]@host/r,".repeat(2000))
			result["checks"] = checks
			passed = not checks.has(false) and passed
		"security_urls":
			var allowed: Array[String] = [
				"ssh://git%40team@example.invalid/repo", "ssh://git@team@example.invalid/repo",
				"ssh://git%3Ateam@example.invalid/repo", "example.invalid:repo@v1.git",
				"[2001:db8::1]:repo@v1.git", "./local:repo@v1.git",
				"./local/repo?token=snapshot", "example.invalid:repo?token=snapshot",
				"ssh://example.invalid/repo?token=snapshot", "file:///neutral/repo?token=snapshot",
			]
			for index: int in range(allowed.size()):
				var name := "allowed-" + str(index)
				provider.call("test_create_remote", name, allowed[index])
				passed = provider.call("test_get_remotes").has(name) and passed
		"security_origins":
			var pairs: Array = [
				["https://[2001:db8::1]/repo", "https://2001:db8::1/repo"],
				["https://[2001:db8::1]:444/repo", "https://2001:db8::1:444/repo"],
				["https://%65xample.invalid/repo", "https://example.invalid/repo"],
				["https://example.invalid:/repo", "https://example.invalid:443/repo"],
				["https://example.invalid./repo", "HTTPS://EXAMPLE.invalid:0443/repo"],
				["example.invalid:repo with spaces", "ssh://example.invalid/repo"],
			]
			var checks: Array = []
			for pair: Array in pairs:
				var actual: Array = provider.call("test_credential_requests", pair[0], [pair[1]], 1, "")
				checks.append(actual == [true])
				passed = actual == [true] and passed
			for changed: String in ["http://[2001:db8::1]/repo", "https://[2001:db8::2]/repo", "https://[2001:db8::1]:444/repo"]:
				passed = provider.call("test_credential_requests", "https://[2001:db8::1]/repo", [changed], 1, "") == [false] and passed
			result["checks"] = checks
		"security_overlap":
			provider.call("test_set_credentials", "abc", "abcdefSECRET", "", "", "")
			passed = provider.call("test_sanitize_output", "abcdefSECRET abc abcdefSECRET") == "[redacted] [redacted] [redacted]" and passed
			provider.call("test_set_credentials", "aba", "bab", "", "", "")
			passed = provider.call("test_sanitize_output", "ababa") == "[redacted]" and passed
		"security_long_output":
			for length: int in [64, 256, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]:
				var text := "x".repeat(length)
				passed = provider.call("test_sanitize_output", text) == text and passed
				provider.call("test_progress_packets", [text, "\n"])
				var sensitive := "ssh://" + text + ":LONG_SECRET@host/repo?token=QUERY_SECRET"
				var safe: String = provider.call("test_sanitize_output", sensitive)
				passed = not safe.contains("LONG_SECRET") and not safe.contains("QUERY_SECRET") and passed
				provider.call("test_progress_packets", [sensitive, "\n"])
			var packets: Array[String] = []
			for index: int in range(1024):
				packets.append("x".repeat(64))
			packets.append("fixture-password\n")
			provider.call("test_progress_packets", packets)
			packets.clear()
			for index: int in range(1024):
				packets.append("x".repeat(60))
			packets.append("fixture-")
			packets.append("password\n")
			provider.call("test_progress_packets", packets)
		"security_cr":
			provider.call("test_progress_packets", ["CR_ONE\r", "\nCR_TWO\rCR_", "THREE\nCR_TAIL"])
			var packets: Array[String] = []
			for index: int in range(1100):
				packets.append("CR_TICK " + "x".repeat(64) + "\r")
			provider.call("test_progress_packets", packets)
		"security_fallback":
			var origin := "ssh://git@example.invalid/repo"
			var attempts: Array = provider.call("test_credential_requests", origin, [origin, origin, origin, origin], 3, "git")
			passed = attempts == [true, true, false, false] and passed
	result["passed"] = passed
	return result
