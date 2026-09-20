import sys as _sys
from types import ModuleType as _ModuleType

from . import guacamole as _guacamole
from . import rdp as _rdp
from . import payloads as _payloads
from . import recordings as _recordings
from . import audit as _audit
from . import commands as _commands
from . import connections as _connections
from . import errors as _errors
from . import file_parsers as _file_parsers
from . import files as _files
from . import monitoring as _monitoring

from .guacamole import (
    find_guacamole_instruction_end,
    guacamole_element,
    guacamole_instruction,
    is_guacamole_internal_instruction,
    parse_guacamole_instruction,
    read_guacamole_instruction,
)
from .rdp import (
    create_rdp_terminal_session,
    greeting_for,
    terminal_protocol_for_host,
)


from .file_parsers import (
    normalize_remote_file_path,
    normalize_remote_file_name,
    normalize_remote_relative_file_path,
    normalize_remote_download_protocol,
    normalize_remote_symlink_target,
    normalize_remote_file_owner,
    normalize_remote_file_octal_mode,
    join_remote_path,
    parent_remote_path,
    parent_remote_entry,
    remote_stat_command,
    parse_remote_stat_output,
    remote_file_properties_payload,
    normalize_remote_stat_identity,
    format_remote_timestamp,
    parse_remote_find_entries,
    parse_remote_ls_entries,
    remote_file_sort_key,
    remote_file_sort_rank,
    natural_sort_key,
)

from .files import (
    list_remote_directory,
    download_remote_file,
    download_remote_file_content,
    stream_remote_file_content,
    upload_remote_file_stream,
    upload_remote_file,
    create_remote_file,
    create_remote_directory,
    create_remote_symlink,
    rename_remote_file,
    delete_remote_file,
    get_remote_file_properties,
    update_remote_file_properties,
    run_remote_file_operation,
    list_remote_directory_with_sftp,
    list_remote_directory_with_scp_enhanced,
    list_remote_directory_with_scp_normal,
    get_remote_file_properties_with_sftp,
    get_remote_file_properties_with_stat,
    resolve_remote_directory_path,
    resolve_remote_file_path,
    run_client_command,
    resolve_remote_identity_names,
    resolve_remote_user_name,
    resolve_remote_group_name,
    run_optional_client_command,
    enrich_remote_entries_with_stat,
    download_remote_file_with_sftp,
    download_remote_file_content_with_sftp,
    stream_remote_file_content_with_sftp,
    stream_remote_file_content_with_scp,
    download_remote_file_with_scp_enhanced,
    download_remote_file_content_with_scp_enhanced,
    download_remote_file_with_scp_normal,
    download_remote_file_content_with_scp_normal,
    upload_remote_file_with_sftp,
    upload_remote_file_with_sftp_stream,
    upload_remote_file_with_ssh_stream,
    ensure_remote_sftp_directory,
    upload_remote_file_with_scp_enhanced,
    upload_remote_file_with_scp_normal,
    encode_remote_download,
)

from .monitoring import (
    get_remote_resource_monitor,
    parse_remote_resource_monitor_output,
    split_monitor_sections,
    parse_monitor_key_values,
    parse_monitor_cpu_line,
    calculate_monitor_cpu_usage,
    parse_monitor_load,
    detect_monitor_cpu_cores,
    parse_monitor_memory,
    parse_monitor_network,
    parse_monitor_network_rates,
    parse_monitor_disks,
    parse_monitor_int,
    parse_monitor_float,
)

from .commands import (
    run_live_terminal_command,
    run_one_shot_ssh_command,
    run_one_shot_ssh_upload,
    run_session_command,
)

from .connections import (
    DEFAULT_TERMINAL_COLS,
    DEFAULT_TERMINAL_ROWS,
    LiveTerminalConnection,
    borrow_sftp_client,
    borrow_ssh_client,
    clear_ssh_client_pool,
    load_private_key,
    normalize_terminal_output,
    open_live_terminal,
    open_ssh_client,
    ssh_client_pool_key,
    should_retry_ssh_connect_error,
)

from .errors import TerminalConnectionError

from .audit import (
    append_audit_output,
    classify_command_risk,
    command_audit_payload,
    create_command_audit,
    create_terminal_session,
    is_session_audit_enabled,
)

from .payloads import (
    group_payload,
    host_payload,
    session_payload,
    terminal_tree_payload,
)

from .recordings import (
    asciicast_header,
    asciicast_event,
    json_dumps,
    initialize_session_recording,
    append_session_recording_event,
    save_session_recording,
)
from .rdp import (
    is_rdp_recording_enabled,
    build_rdp_recording_file,
    build_rdp_connection_parameters,
    clamp_rdp_dimension,
    rdp_recording_root,
    safe_recording_relative_path,
    cleanup_expired_rdp_recordings,
    prune_empty_recording_parents,
)

__all__ = [
    'DEFAULT_TERMINAL_COLS',
    'DEFAULT_TERMINAL_ROWS',
    'LiveTerminalConnection',
    'TerminalConnectionError',
    'append_audit_output',
    'append_session_recording_event',
    'asciicast_event',
    'asciicast_header',
    'build_rdp_connection_parameters',
    'build_rdp_recording_file',
    'calculate_monitor_cpu_usage',
    'clamp_rdp_dimension',
    'classify_command_risk',
    'cleanup_expired_rdp_recordings',
    'borrow_sftp_client',
    'borrow_ssh_client',
    'clear_ssh_client_pool',
    'command_audit_payload',
    'create_command_audit',
    'create_rdp_terminal_session',
    'create_remote_directory',
    'create_remote_file',
    'create_remote_symlink',
    'create_terminal_session',
    'delete_remote_file',
    'detect_monitor_cpu_cores',
    'download_remote_file',
    'download_remote_file_content',
    'download_remote_file_content_with_scp_enhanced',
    'download_remote_file_content_with_scp_normal',
    'download_remote_file_content_with_sftp',
    'download_remote_file_with_scp_enhanced',
    'download_remote_file_with_scp_normal',
    'download_remote_file_with_sftp',
    'encode_remote_download',
    'enrich_remote_entries_with_stat',
    'ensure_remote_sftp_directory',
    'find_guacamole_instruction_end',
    'format_remote_timestamp',
    'get_remote_file_properties',
    'get_remote_file_properties_with_sftp',
    'get_remote_file_properties_with_stat',
    'get_remote_resource_monitor',
    'greeting_for',
    'group_payload',
    'guacamole_element',
    'guacamole_instruction',
    'host_payload',
    'initialize_session_recording',
    'is_guacamole_internal_instruction',
    'is_rdp_recording_enabled',
    'is_session_audit_enabled',
    'join_remote_path',
    'json_dumps',
    'list_remote_directory',
    'list_remote_directory_with_scp_enhanced',
    'list_remote_directory_with_scp_normal',
    'list_remote_directory_with_sftp',
    'load_private_key',
    'natural_sort_key',
    'normalize_remote_download_protocol',
    'normalize_remote_file_name',
    'normalize_remote_file_octal_mode',
    'normalize_remote_file_owner',
    'normalize_remote_file_path',
    'normalize_remote_relative_file_path',
    'normalize_remote_stat_identity',
    'normalize_remote_symlink_target',
    'normalize_terminal_output',
    'open_live_terminal',
    'open_ssh_client',
    'ssh_client_pool_key',
    'parent_remote_entry',
    'parent_remote_path',
    'parse_guacamole_instruction',
    'parse_monitor_cpu_line',
    'parse_monitor_disks',
    'parse_monitor_float',
    'parse_monitor_int',
    'parse_monitor_key_values',
    'parse_monitor_load',
    'parse_monitor_memory',
    'parse_monitor_network',
    'parse_monitor_network_rates',
    'parse_remote_find_entries',
    'parse_remote_ls_entries',
    'parse_remote_resource_monitor_output',
    'parse_remote_stat_output',
    'prune_empty_recording_parents',
    'rdp_recording_root',
    'read_guacamole_instruction',
    'remote_file_properties_payload',
    'remote_file_sort_key',
    'remote_file_sort_rank',
    'remote_stat_command',
    'rename_remote_file',
    'resolve_remote_directory_path',
    'resolve_remote_file_path',
    'resolve_remote_group_name',
    'resolve_remote_identity_names',
    'resolve_remote_user_name',
    'run_client_command',
    'run_live_terminal_command',
    'run_one_shot_ssh_command',
    'run_one_shot_ssh_upload',
    'run_optional_client_command',
    'run_remote_file_operation',
    'run_session_command',
    'safe_recording_relative_path',
    'save_session_recording',
    'session_payload',
    'should_retry_ssh_connect_error',
    'split_monitor_sections',
    'stream_remote_file_content',
    'stream_remote_file_content_with_scp',
    'stream_remote_file_content_with_sftp',
    'terminal_protocol_for_host',
    'terminal_tree_payload',
    'update_remote_file_properties',
    'upload_remote_file',
    'upload_remote_file_stream',
    'upload_remote_file_with_scp_enhanced',
    'upload_remote_file_with_scp_normal',
    'upload_remote_file_with_sftp',
    'upload_remote_file_with_sftp_stream',
    'upload_remote_file_with_ssh_stream',
]

_SERVICE_IMPLEMENTATION_MODULES = (
    _guacamole,
    _rdp,
    _payloads,
    _recordings,
    _audit,
    _commands,
    _connections,
    _errors,
    _file_parsers,
    _files,
    _monitoring,
)
_MISSING = object()


class _ServiceModule(_ModuleType):
    def __setattr__(self, name, value):
        previous = getattr(self, name, _MISSING)
        super().__setattr__(name, value)
        if previous is _MISSING:
            return
        for implementation_module in _SERVICE_IMPLEMENTATION_MODULES:
            if getattr(implementation_module, name, _MISSING) is previous:
                setattr(implementation_module, name, value)


_sys.modules[__name__].__class__ = _ServiceModule
