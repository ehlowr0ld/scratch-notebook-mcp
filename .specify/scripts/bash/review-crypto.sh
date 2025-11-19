#!/usr/bin/env bash
# Shared encryption/decryption utilities for review artifacts.
# Requires OpenSSL and a repository-managed key file. The key path may be set via
# SPECKIT_REVIEW_KEY_FILE or defaults to .specify/secret/review-key relative to repo root.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_binary() {
  local bin="$1"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $bin" >&2
    exit 2
  fi
}

require_binary openssl
require_binary python3

get_key_file() {
  local repo_root="$(get_repo_root)"
  local default_key="${repo_root}/.specify/secret/review-key"
  local key_path="${SPECKIT_REVIEW_KEY_FILE:-${default_key}}"

  if [[ ! -f "${key_path}" ]]; then
    echo "ERROR: review encryption key not found. Set SPECKIT_REVIEW_KEY_FILE or create ${key_path}" >&2
    exit 2
  fi

  printf '%s' "${key_path}"
}

encrypt_artifact() {
  local plaintext="$1"
  local encrypted="$2"

  if [[ ! -f "${plaintext}" ]]; then
    echo "ERROR: encrypt_artifact missing plaintext file ${plaintext}" >&2
    exit 2
  fi

  local key_file
  key_file="$(get_key_file)"

  openssl enc -aes-256-cbc -pbkdf2 -salt \
    -in "${plaintext}" \
    -out "${encrypted}" \
    -pass file:"${key_file}" >/dev/null 2>&1
}

decrypt_artifact_to_tmp() {
  local encrypted="$1"

  if [[ ! -f "${encrypted}" ]]; then
    echo "ERROR: decrypt_artifact_to_tmp missing encrypted file ${encrypted}" >&2
    exit 2
  fi

  local key_file
  key_file="$(get_key_file)"

  local tmp
  tmp="$(mktemp)"
  chmod 600 "${tmp}"

  if ! openssl enc -aes-256-cbc -d -pbkdf2 \
      -in "${encrypted}" \
      -out "${tmp}" \
      -pass file:"${key_file}" >/dev/null 2>&1; then
    rm -f "${tmp}"
    echo "ERROR: failed to decrypt ${encrypted}" >&2
    exit 2
  fi

  printf '%s' "${tmp}"
}

write_encrypted_json() {
  local json_payload="$1"
  local dest="$2"

  local tmp
  tmp="$(mktemp)"
  chmod 600 "${tmp}"
  printf '%s' "${json_payload}" > "${tmp}"
  encrypt_artifact "${tmp}" "${dest}"
  rm -f "${tmp}"
}

append_encrypted_jsonl() {
  local json_line="$1"
  local dest="$2"

  local tmp
  tmp="$(mktemp)"
  chmod 600 "${tmp}"

  if [[ -f "${dest}" ]]; then
    local decrypted
    decrypted="$(decrypt_artifact_to_tmp "${dest}")"
    cat "${decrypted}" > "${tmp}"
    rm -f "${decrypted}"
  fi

  printf '%s\n' "${json_line}" >> "${tmp}"
  encrypt_artifact "${tmp}" "${dest}"
  rm -f "${tmp}"
}

replace_with_encrypted_file() {
  local plaintext="$1"
  local dest="$2"
  encrypt_artifact "${plaintext}" "${dest}"
}
