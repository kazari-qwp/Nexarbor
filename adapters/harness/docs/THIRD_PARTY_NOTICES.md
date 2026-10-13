# Third-party runtime notices

The shipped backend includes CPython, NumPy, pandas, filelock and PyInstaller-built bootloader/runtime files. These components retain their upstream licenses. Included distribution metadata and license files are under runtime/datanet-backend/_internal where provided by the build tools.

Harness SDK services are supplied by the installed host. The official DeepSeek Harness 0.2.0-rc.2 AgentLoop driver and its invariant are included with a request-tail extension under runtime/harness-agent-loop, with the upstream MIT LICENSE. Its runtime dependency zod retains its upstream license. The independent development copy of Electron used during troubleshooting is not part of the plugin tarball.

Original DataNet source belongs to the original project and is preserved rather than relicensed by this adapter. Before a public release, perform a full third-party license inventory and add the project's chosen license; this local validation package does not establish a new blanket license.
