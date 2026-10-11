export const MODES = [
  {
    value: 'all',
    label: 'All',
    scopeLabel: 'Scope',
    scopeText: 'Everything indexed',
    hint: 'Searches docs, code and wikis together',
    placeholder: 'Ask anything about your company…',
    examples: ['How do I set up my local environment?', 'Who approves staging database access?'],
  },
  {
    value: 'gittalk',
    needs: 'code', // content type the user's department must be allowed (see AuthContext can())
    label: 'GitTalk',
    scopeLabel: 'Repository',
    scopePlaceholder: 'https://github.com/owner/repo',
    needsScope: true,
    hint: 'Explains code and points to file paths',
    placeholder: 'Ask about the code in this repository…',
    examples: ['Where is the search logic implemented?', 'How does ingestion split files into chunks?'],
  },
  {
    value: 'docsense',
    needs: 'doc',
    label: 'Docsense',
    scopeLabel: 'Document',
    scopePlaceholder: 'file name',
    needsScope: true,
    hint: 'Answers from one uploaded document',
    placeholder: 'Ask about this document…',
    examples: ['Summarize the main points of this document', 'What does it say about deadlines?'],
  },
  {
    value: 'sharebase',
    needs: 'wiki',
    label: 'Sharebase',
    scopeLabel: 'Wiki',
    scopeText: 'All wikis',
    hint: 'Searches team wikis only',
    placeholder: 'Ask the team wikis…',
    examples: ['What is our deploy process?', 'Where is the incident runbook?'],
  },
];

export const modeOf = (value) => MODES.find((m) => m.value === value) ?? MODES[0];

export const DEPARTMENTS = ['Engineering', 'Platform', 'Product', 'Design', 'People', 'Sales'];
