extends SceneTree

const RESULT_PREFIX := "REDOT_GIT_PRIVATE_TEST="


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	for _frame: int in range(300):
		if ClassDB.class_exists(&"GitPlugin"):
			break
		await process_frame

	var provider: Object = ClassDB.instantiate(&"GitPlugin") if ClassDB.class_exists(&"GitPlugin") else null
	if provider == null:
		_finish({"passed": false, "reason": "GitPlugin was not instantiable"})
		return

	var transport := OS.get_environment("REDOT_GIT_TRANSPORT")
	var remote_url := OS.get_environment("REDOT_GIT_REMOTE_URL")
	var result: Dictionary = {
		"transport": transport,
		"initialize": provider.call("test_initialize", ProjectSettings.globalize_path("res://")),
	}
	if not result.initialize:
		result["passed"] = false
		_finish(result, provider)
		return

	if transport == "https":
		result["ca_configured"] = provider.call("test_set_ca_certificate", ProjectSettings.globalize_path("res://ca.crt"))
	else:
		result["ca_configured"] = true

	provider.call(
		"test_set_credentials",
		OS.get_environment("REDOT_GIT_USERNAME"),
		OS.get_environment("REDOT_GIT_PASSWORD"),
		OS.get_environment("REDOT_GIT_PUBLIC_KEY"),
		OS.get_environment("REDOT_GIT_PRIVATE_KEY"),
		OS.get_environment("REDOT_GIT_PASSPHRASE"),
	)
	var negative_case := OS.get_environment("REDOT_GIT_NEGATIVE_CASE")
	if not negative_case.is_empty():
		_run_negative(provider, result, remote_url, negative_case)
		return
	provider.call("test_create_remote", "origin", remote_url)
	result["remotes"] = provider.call("test_get_remotes")
	provider.call("test_pull", "origin")
	var upstream_path := "res://upstream-" + transport + ".txt"
	result["pulled_text"] = FileAccess.get_file_as_string(upstream_path)

	var pushed_name := "provider-" + transport + ".txt"
	var pushed_file := FileAccess.open("res://" + pushed_name, FileAccess.WRITE)
	pushed_file.store_string("pushed over " + transport + "\n")
	pushed_file.close()
	provider.call("test_stage_file", pushed_name)
	provider.call("test_commit", "Provider " + transport + " commit")
	result["local_tip"] = provider.call("test_get_previous_commits", 1)
	provider.call("test_push", "origin", false)
	result["shutdown"] = provider.call("test_shutdown")
	result["credentials_empty"] = provider.call("test_credentials_empty")
	result["passed"] = (
		result.initialize
		and result.ca_configured
		and result.remotes.has("origin")
		and result.pulled_text.replace("\r\n", "\n") == "upstream over " + transport + "\n"
		and result.local_tip.size() == 1
		and result.shutdown
		and result.credentials_empty
	)
	_finish(result, provider)


func _run_negative(provider: Object, result: Dictionary, remote_url: String, negative_case: String) -> void:
	var before: Array = provider.call("test_get_previous_commits", 1)
	var remote := "negative-" + negative_case
	provider.call("test_create_remote", remote, remote_url)
	result["negative_case"] = negative_case
	if negative_case == "redirect":
		provider.call("test_fetch", remote)
		provider.call("test_pull", remote)
		provider.call("test_push", remote, false)
	else:
		var file := FileAccess.open("res://rejected.txt", FileAccess.WRITE)
		file.store_string("rejected by receive hook\n")
		file.close()
		provider.call("test_stage_file", "rejected.txt")
		provider.call("test_commit", "Rejected transport commit")
		provider.call("test_push", remote, false)
	var after: Array = provider.call("test_get_previous_commits", 1)
	result["shutdown"] = provider.call("test_shutdown")
	result["credentials_empty"] = provider.call("test_credentials_empty")
	result["passed"] = result.initialize and result.ca_configured and result.shutdown and result.credentials_empty and not after.is_empty()
	if negative_case == "redirect":
		result["passed"] = result.passed and before == after
	_finish(result, provider)


func _finish(result: Dictionary, provider: Object = null) -> void:
	var freed := true
	if is_instance_valid(provider):
		provider.call("test_shutdown")
		var instance_id := provider.get_instance_id()
		provider.free()
		freed = not is_instance_id_valid(instance_id)
	result["providers_freed"] = freed
	result["passed"] = result.get("passed", false) and freed
	print(RESULT_PREFIX + JSON.stringify(result))
	if not result.get("passed", false):
		quit(1)
