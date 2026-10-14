"""Preserve Harness's inherited capability ACE when CPython requests mode 0700."""
import os


def install():
    if os.name != 'nt':
        return
    import ctypes as c
    from ctypes import wintypes as w
    import re
    adv = c.WinDLL('advapi32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    ptr = c.c_void_p
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    adv.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, ptr, w.DWORD, c.POINTER(w.DWORD)]
    adv.ConvertSidToStringSidW.argtypes = [ptr, c.POINTER(ptr)]
    adv.GetNamedSecurityInfoW.argtypes = [w.LPWSTR, c.c_int, w.DWORD, ptr, ptr, ptr, ptr, c.POINTER(ptr)]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [ptr, w.DWORD, w.DWORD, c.POINTER(ptr), ptr]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(ptr), ptr]
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.LocalFree.argtypes = [ptr]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    class SidAttributes(c.Structure):
        _fields_ = [('sid', ptr), ('attributes', w.DWORD)]
    class Groups(c.Structure):
        _fields_ = [('count', w.DWORD), ('groups', SidAttributes * 1)]
    class SecurityAttributes(c.Structure):
        _fields_ = [('length', w.DWORD), ('descriptor', ptr), ('inherit', w.BOOL)]
    kernel.CreateDirectoryW.argtypes = [w.LPCWSTR, c.POINTER(SecurityAttributes)]

    def sid_string(sid):
        value = ptr()
        if not adv.ConvertSidToStringSidW(sid, c.byref(value)):
            raise c.WinError(c.get_last_error())
        try:
            return c.wstring_at(value)
        finally:
            kernel.LocalFree(value)

    token = w.HANDLE()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
        return
    def info(kind):
        size = w.DWORD()
        adv.GetTokenInformation(token, kind, None, 0, c.byref(size))
        buffer = c.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, kind, buffer, size, c.byref(size)):
            raise c.WinError(c.get_last_error())
        return buffer
    try:
        restricted = info(11)
        count = c.cast(restricted, c.POINTER(w.DWORD)).contents.value
        entries = (SidAttributes * count).from_buffer(restricted, Groups.groups.offset)
        capabilities = {sid_string(item.sid) for item in entries}
        capabilities = {sid for sid in capabilities if re.fullmatch(r'S-1-4-\d+-\d+(?:-1)?', sid)}
        if not capabilities:
            return
        user = sid_string(c.cast(info(1), c.POINTER(SidAttributes)).contents.sid)
    finally:
        kernel.CloseHandle(token)

    if getattr(os.mkdir, '_datanet_private_dirs', False):
        return
    original = os.mkdir
    def mkdir(path, mode=0o777, *, dir_fd=None):
        if mode != 0o700 or dir_fd is not None:
            return original(path, mode, dir_fd=dir_fd)
        name = os.fsdecode(os.fspath(path))
        parent = os.path.dirname(os.path.abspath(name))
        descriptor, text = ptr(), ptr()
        error = adv.GetNamedSecurityInfoW(parent, 1, 4, None, None, None, None, c.byref(descriptor))
        if error:
            return original(path, mode)
        try:
            if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 4, c.byref(text), None):
                return original(path, mode)
            parent_acl = c.wstring_at(text)
        finally:
            if text:
                kernel.LocalFree(text)
            kernel.LocalFree(descriptor)
        grants = []
        for ace in re.findall(r'\(([^()]*)\)', parent_acl):
            parts = ace.split(';')
            if len(parts) == 6 and parts[0] == 'A' and parts[5] in capabilities and 'CI' in parts[1]:
                grants.append(f'(A;OICI;{parts[2]};;;{parts[5]})')
        if not grants:
            return original(path, mode)
        # Keep CPython's private user/admin/system DACL, plus the already granted
        # sandbox capability. Create atomically; never widen a parent or token.
        acl = f'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{user})' + ''.join(grants)
        security = ptr()
        if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(acl, 1, c.byref(security), None):
            raise c.WinError(c.get_last_error())
        try:
            attributes = SecurityAttributes(c.sizeof(SecurityAttributes), security, False)
            if not kernel.CreateDirectoryW(name, c.byref(attributes)):
                error = c.get_last_error()
                failure = c.WinError(error)
                failure.filename = name
                raise failure
        finally:
            kernel.LocalFree(security)
    mkdir._datanet_private_dirs = True
    os.mkdir = mkdir
