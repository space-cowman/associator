// Shapes returned by the api (only the fields the UI uses).

export type Tally = { up: number; down: number };
export type VoteCounts = { human: Tally; agent: Tally };

export type Group = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  member_count: number;
  thread_count: number;
  joined: boolean;
};

export type Profile = {
  handle: string;
  joined_at: string;
  questions: number;
  answers: number;
  satisfied: number;
  reputation: number;
};

export type ProfileAnswer = {
  id: string;
  thread_id: string;
  group: string;
  thread_text: string;
  text: string;
  by_agent: boolean;
  via: Via;
  created_at: string;
  satisfied: boolean;
  votes: VoteCounts;
};

export type Notification = {
  id: string;
  kind: "reply" | "satisfied";
  thread_id: string;
  thread_text: string;
  reply_id: string | null;
  actor: string | null;
  by_agent: boolean;
  via: Via | null;
  created_at: string;
  read: boolean;
};

export type Via = "person" | "assisted" | "agent";

export type Sort = "hot" | "new" | "top";
export type Window = "day" | "week" | "month" | "all";

export type Attachment = {
  id: string;
  kind: "image" | "video" | "pdf" | "text";
  filename: string;
  content_type: string;
  size_bytes: number;
};

export type Thread = {
  id: string;
  group: string;
  text: string;
  author: string | null;
  by_agent: boolean;
  created_at: string;
  satisfied_reply_id: string | null;
  reply_count: number;
  votes: VoteCounts;
  warnings: string[];
  attachments: Attachment[];
};

export type Reply = {
  id: string;
  thread_id: string;
  parent_id: string | null;
  depth: number;
  reply_to_id: string | null;
  reply_to_author: string | null;
  author: string | null;
  by_agent: boolean;
  via: Via;
  text: string;
  created_at: string;
  votes: VoteCounts;
  warnings: string[];
  attachments: Attachment[];
};

export type Draft = {
  id: string;
  thread_id: string;
  parent_id: string | null;
  status: "pending" | "approved" | "discarded";
  mode: "ask_my_ai" | "platform_ai" | "mcp";
  text: string;
  instruction: string;
  model_label: string | null;
  warnings: string[];
  reply_id: string | null;
  created_at: string;
  models_used: string[];
  plan: { kind: string; task: string; model: string | null }[];
  memory_used: string[];
};

export type SimilarThread = { id: string; group: string; text: string; answered: boolean };

export type SavedModel = {
  id: string;
  provider: string;
  model: string;
  label: string | null;
  strengths: string[];
  enabled: boolean;
  key_last4: string;
  created_at: string;
};

export type MemoryItem = {
  id: string;
  text: string;
  searchable: boolean;
  created_at: string;
  updated_at: string;
};

export type AccessToken = {
  id: string;
  name: string;
  token_last4: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

export type Conversation = {
  id: string;
  kind: "cluster" | "direct";
  title: string;
  my_state: "invited" | "active";
  my_role: "admin" | "member";
  invited_by: string | null;
  member_count: number;
  ai_enabled: boolean;
  ai_sharing: boolean;
  created_at: string;
};

export type ConversationMember = { handle: string; role: "admin" | "member"; state: "invited" | "active" };

export type ConversationDetail = Conversation & { members: ConversationMember[] };
