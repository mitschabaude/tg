Run TypeScript scripts/CLIs directly with `node`; this project uses Node's native type stripping, so do not introduce `tsx` or require a compile step for local CLI execution.
Do not add backwards-compatibility mechanisms or deprecated aliases; this is not a production project, it has a single user, and old commands should be renamed or removed directly.
