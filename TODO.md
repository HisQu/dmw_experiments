# Todo list

Treat this as the parking lot for actionable problems discovered while working but intentionally left unresolved.


<br>

> [!CAUTION]
> This is git-tracked: Never record secrets, absolute paths, credentials, private host data, or speculative security claims. Use only relative paths. 


> [!IMPORTANT]
> 
> ## Rules
> 1) Do not remove this header and TOC. THis is supposed to stay.
> 1) Newest at the top, but below `## Ignore`.
> 1) Do not suggest issues for paths that are under `## Ignore`
> 1) Append a new entry only when the observation is real, actionable, not already listed, and out of scope for the current change. Do not modify `TODO.md` when there is nothing useful to add.
> 1) If an issue is new and related to another issue, reference it in the `Suggested next step`. Do not create a new entry for the same problem. Place the reference in both entries (bi-directional).
> 1) If an issue was resolved, remove it and make an entry in the CHANGELOG.md.
> 1) **Types:**
>       - **Bug risk**: Potential defect with concrete evidence, not yet confirmed.
>       - **Code smell**: Implementation, architectural, maintainability or clarity issue that is not currently a defect.
>       - **Docs drift**: Documentation is stale, incomplete, or inconsistent.
>       - **Tooling**: Issue with build, test, lint, type-check, and general slowdown of developer workflow.
>       - **Security**: Evidence-backed security risk. Use Question for uncertainty.
>       - **Question**: Design, behavior, or ownership uncertainty needing investigation & maybe decision.
> 
> 1) **Priorities:**
>       - **P1**: Should be handled ASAP.
>       - **P2**: Should be handled before next release or milestone.
>       - **P3**: Useful cleanup for a later focused pass.
> 1) **Effort:**
>       - **E1**: Issue deserves its own focused pass.
>       - **E2**: Can be batched with a few other issues.
>       - **E3**: Can be batched with many other issues.
> 1) **Format:**
> ```markdown
> 
> <br>
> 
> # YYYY-MM-DD <!-- today's date -->
>
> ## <Priority> / <Effort> [<Type>] - *Short problem title*
> - **Area:**  `path/or/symbol`
> - **Observed while:** short context
> - **Why not fixed now:** scope, risk, uncertainty, or user decision needed
> - **Evidence:** concrete observation
> - **Context:** explanation to ensure the problem is understood in the big-picture of the repo.
> - **Suggested next step:** smallest reasonable follow-up. If applicable, reference related todos [here](#todo-list).
> 
> ## <Priority> / <Effort> [<Type>] - *Short problem title*
> - **Area:** `path/or/symbol`
> - ...
> 
> <br>
> 
> # YYYY-MM-DD  <!-- today's date -->
>
> ## <Priority> / <Effort> [<Type>] - *Short problem title*
> - **Area:** `path/or/symbol`
> - ...
> ```



<br>

---

<br>

## Table Of Contents

1. [Todo list](#todo-list)
   1. [Table Of Contents](#table-of-contents)
   2. [Ignore](#ignore)
2. [\< YYYY-MM-DD \>](#-yyyy-mm-dd-)
   1. [P3 / E1 \[Code smell\] -  *Lorem ipsum dolor*](#p3--e1-code-smell----lorem-ipsum-dolor)
   2. [P1 / E3 \[Bug risk\] -  *dolor sit amet*](#p1--e3-bug-risk----dolor-sit-amet)
3. [YYYY-MM-DD](#yyyy-mm-dd)
   1. [P3 \[Code smell\] -  *Amet consectetur adipiscing elit*](#p3-code-smell----amet-consectetur-adipiscing-elit)
   2. [P1 \[Bug risk\] -  *Elit sed do eiusmod*](#p1-bug-risk----elit-sed-do-eiusmod)

<br>


---

<br>

## Ignore
- `publications/`

<br>

---

<br>


<!-- Example, remove this during first pass -->

# < YYYY-MM-DD >

## P3 / E1 [Code smell] -  *Lorem ipsum dolor*
- **Area:** `sit/amet`
- **Observed while:** amet consectetur adipiscing elit
- **Evidence:** elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua
- **Why not fixed now:** aliqua ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat
- **Suggested next step:** Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.


## P1 / E3 [Bug risk] -  *dolor sit amet*
- **Area:** `amet/consectetur/adipiscing`
- ...

<br>

# YYYY-MM-DD

## P3 [Code smell] -  *Amet consectetur adipiscing elit*
- **Area:** `elit/sed/do/eiusmod`
- ...

## P1 [Bug risk] -  *Elit sed do eiusmod*
- **Area:** `eiusmod/tempor/incididunt/ut/labore`
- ...