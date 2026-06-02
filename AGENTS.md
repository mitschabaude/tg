Run TypeScript scripts/CLIs directly with `node`; this project uses Node's native type stripping, so do not introduce `tsx` or require a compile step for local CLI execution.
Do not add backwards-compatibility mechanisms or deprecated aliases unless explicitly requested; old commands should usually be renamed or removed directly.
