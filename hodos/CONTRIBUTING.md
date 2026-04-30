# Contributing to Hodos

Thanks for thinking about contributing. Hodos is a small project today
and the contribution process is deliberately light. This will evolve
as the project grows.

## What you can contribute

- **Engine code** — improvements to harvesting, inference, taxonomy,
  CHRONICLE schema, publishing, or chat layers.
- **Schema work** — improvements to the CHRONICLE schema, taxonomy
  format, or other declarative interfaces.
- **Sample / example data** — synthetic example CHRONICLE entries,
  taxonomies, or example applications that show how Hodos is used.
- **Documentation** — anything that makes the project easier to
  understand, install, run, or extend.

## What you cannot contribute (read this first)

Hodos is the open-source engine. **CJI is a separate, closed product
built on top of Hodos.** The CJI CHRONICLE entries (real banking
incident analyses, the CHR-001..019 series and beyond), the CJI
brand surface, and CJI's partner data are NOT part of this
repository and are not contributable here.

If your contribution adds, modifies, or references real-world
proprietary data — incident analyses naming specific firms, real
customer feedback, customer-identifying data — it does not belong
in Hodos. Open a discussion before proposing anything in that
space.

For more on the CJI/Hodos boundary, see HODOS_NAMING.md.

## How to contribute

1. **Open an issue** describing what you want to do, before writing
   code. This saves both of us time if it turns out the change isn't
   a fit, or if there's a better path.
2. **Fork the repository** and make your changes on a branch.
3. **Sign your commits with the DCO** (see next section).
4. **Open a pull request** with a clear description of what you
   changed and why.
5. **Be patient.** This project is maintained by one person right
   now. Reviews may take time. The bar is "this is clearly an
   improvement, with no obvious regressions" — not perfection.

## Developer Certificate of Origin (DCO)

Hodos uses the Developer Certificate of Origin, version 1.1 — the
same model used by the Linux kernel and many other open-source
projects. By signing off on a commit, you certify the following:

> By making a contribution to this project, I certify that:
>
> (a) The contribution was created in whole or in part by me and I
>     have the right to submit it under the open source license
>     indicated in the file; or
>
> (b) The contribution is based upon previous work that, to the best
>     of my knowledge, is covered under an appropriate open source
>     license and I have the right under that license to submit that
>     work with modifications, whether created in whole or in part by
>     me, under the same open source license (unless I am permitted to
>     submit under a different license), as indicated in the file; or
>
> (c) The contribution was provided directly to me by some other
>     person who certified (a), (b) or (c) and I have not modified it.
>
> (d) I understand and agree that this project and the contribution
>     are public and that a record of the contribution (including all
>     personal information I submit with it, including my sign-off) is
>     maintained indefinitely and may be redistributed consistent with
>     this project or the open source license(s) involved.

To sign off on a commit, use:

    git commit -s -m "your commit message"

This appends a `Signed-off-by: Your Name <your.email@example.com>`
line to the commit message. Use your real name (or a pseudonym you
use consistently across your open-source work) and an email you can
be reached at.

If you forget to sign off, amend the most recent commit with:

    git commit --amend -s --no-edit

## License

By contributing, you agree that your contribution will be licensed
under the Apache License, Version 2.0 — the same license that
covers the rest of this repository. See LICENSE for details.

## Code of conduct

Be respectful. Disagreement is fine; personal attacks are not. If
something feels off, contact the maintainer at hello@cjipro.com.

A more detailed code of conduct may be added as the project grows.
