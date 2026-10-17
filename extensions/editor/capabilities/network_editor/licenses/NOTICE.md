# Network workbench routing dependencies

These unmodified upstream dependencies are used only by the optional editor frontend. Network permissions and Agent execution remain owned by Nexarbor. Versions and package integrity are pinned in `frontends/network-editor/package-lock.json`.

| Library | Version | License | Corresponding upstream source |
|---|---|---|---|
| ELK.js | 0.12.0 | EPL-2.0 (chosen distribution license) | https://github.com/kieler/elkjs/tree/ff5771d7165445c42c408bb8a090c8035272218c |
| elkjs-libavoid | 0.5.0 | MIT | https://github.com/MrMint/elkjs-libavoid/tree/24b98cd4393eb55111ec21c35aba3df736f5b3f1 |
| libavoid-js | 0.5.0-beta.5 | LGPL-2.1-or-later | https://github.com/Aksem/libavoid-js/tree/5062a42fbd82fff562afeebcbb7b1ed45eed8e75 |

License texts are included next to this notice. libavoid-js supplies the unmodified, separately served `libavoid-*.wasm` asset; its JavaScript binding and the routing adapter are bundled into the separate routing Worker. libavoid-js provides build instructions and the upstream Adaptagrams source reference in its pinned repository, including its submodule version.

To replace/relink a library, change its npm dependency in `frontends/network-editor`, run `npm install --ignore-scripts`, then `npm run build`. The frontend source and build configuration are supplied in this repository. The generated webpage, Worker and WASM files live in this component's `web/` directory; no application compiler is required when using the prebuilt workbench. No upstream library sources were modified.

Archify's routing design was reviewed at https://github.com/tt-a1i/archify/tree/88d1ae4498b6a1df610badf690c5406882622d15. No Archify source is included.
