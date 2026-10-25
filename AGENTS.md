# Battle Logger boundary

Read MAIN_DIRECTORY.md and PROJECT_STATUS.md first. Develop only inside this folder.
Sibling projects, synced files, game executables, and sources are read-only.
Reuse the meter readers and existing exports. No full executable/xref scans or Ghidra launches.
Default collection/UI refresh is 1 sample/second; supported slower rates are 0.5 and 0.2.
Native reader -> versioned neutral sample -> aggregation/logging -> UI/report. Preserve this separation for a later mod collector.
Do not convert hypotheses into measured statistics. Retain unknown fields, sampled estimates, gaps and incomplete intervals explicitly.
Full enemy data may be collected. Show it live only when the user enables the labeled debugging view.
Keep diagnostics and tests focused. Update status only after meaningful progress. No ZIPs.
