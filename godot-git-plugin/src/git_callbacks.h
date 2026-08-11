#pragma once

#include "godot_cpp/variant/array.hpp"
#include "godot_cpp/variant/string.hpp"
#include "git2.h"

class GitPlugin;
struct Credentials;

struct DiffHelper {
	godot::Array *diff_hunks;
	GitPlugin *git_plugin;
};

godot::String sanitize_git_output(const godot::String &text, const Credentials *credentials = nullptr);
bool git_url_contains_credentials(const godot::String &url);

extern "C" int progress_cb(const char *str, int len, void *data);
extern "C" int update_cb(const char *refname, const git_oid *a, const git_oid *b, void *data);
extern "C" int transfer_progress_cb(const git_indexer_progress *stats, void *payload);
extern "C" int fetchhead_foreach_cb(const char *ref_name, const char *remote_url, const git_oid *oid, unsigned int is_merge, void *payload);
extern "C" int mergehead_foreach_cb(const git_oid *oid, void *payload);
extern "C" int credentials_cb(git_cred **out, const char *url, const char *username_from_url, unsigned int allowed_types, void *payload);
extern "C" int push_transfer_progress_cb(unsigned int current, unsigned int total, size_t bytes, void *payload);
extern "C" int push_update_reference_cb(const char *refname, const char *status, void *data);
extern "C" int diff_hunk_cb(const git_diff_delta *delta, const git_diff_hunk *range, void *payload);
