import type { Metadata } from "next";
import { LegalPage } from "@/components/Legal";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = { title: `Privacy Policy · ${LEGAL.service}` };

const L = LEGAL;

/** The Privacy Policy. */
export default function Privacy() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        This policy explains what personal data {L.service} (&ldquo;we&rdquo;, &ldquo;us&rdquo;), operated by {L.operator},
        collects when you use {L.site} and its connected tools (including the MCP connector for AI apps), why, who it is shared
        with, how long it is kept and what your rights are. It is written to meet the Digital Personal Data Protection Act, 2023
        and its Rules (&ldquo;DPDP&rdquo;), the Information Technology Act, 2000 and the rules made under it. For DPDP purposes,
        {" "}{L.operator} is the Data Fiduciary.
      </p>

      <h2>1. The short version</h2>
      <ul>
        <li>You sign in with GitHub or Google. We receive only an account number from them, never your password, and we do not ask for your email, name or photo.</li>
        <li>Publicly you are only your chosen <b>@handle</b>. Everything you post in public clusters (questions, answers, votes, files) is <b>public</b>.</li>
        <li><b>Private clusters and Messages are private to their members</b>: other people on Associator cannot see them. We store them on our servers, encrypted at rest. They are <b>not end-to-end encrypted</b>: our systems can read them, and authorised staff may look at them only to handle a report, keep the service safe, or when the law requires.</li>
        <li>AI features send the text you choose to an AI provider. Every AI-written answer is shown to you for approval before anything is posted.</li>
        <li>We keep logs and some records for security, quality, abuse prevention and legal reasons, as described below.</li>
        <li>We do <b>not</b> sell your personal data and do not use it for advertising.</li>
      </ul>

      <h2>2. What we collect</h2>
      <h3>From you</h3>
      <ul>
        <li><b>Account:</b> your @handle, the sign-in provider (GitHub or Google), a keyed one-way code derived from that provider&apos;s account number (so the number itself is not stored), and when you accepted these terms.</li>
        <li><b>Content:</b> questions, answers, formatting, attachments (images, PDFs, text files, short videos), votes, &ldquo;Satisfied&rdquo; marks, clusters you create or join.</li>
        <li><b>AI use:</b> the instructions you type for &ldquo;Ask my AI&rdquo; or &ldquo;Platform AI&rdquo;, the drafts produced, whether you approved, edited or discarded them, and which model was used.</li>
        <li><b>Your own AI keys</b> (optional): stored encrypted with a cloud key-management service and decrypted only to make the call you asked for. We never show them back to anyone, including you.</li>
        <li><b>Access tokens</b> you create for AI apps: we store only a one-way hash.</li>
        <li><b>Private chats</b> (private clusters and Messages):
          <ul>
            <li>who is in each chat, its name, roles, invitations, message requests and the people you block;</li>
            <li>the messages and files you send, stored encrypted at rest (with keys held in a cloud key-management service), with who sent them and when;</li>
            <li>files are checked like public attachments (type, size, location data removed from photos) and shared only through short-lived links for members.</li>
          </ul>
          We do not read private chats as a matter of course. Access is limited to handling reports, security and legal requests; the messages you choose to send to an AI go to its provider as described in section 5.
        </li>
        <li><b>Reports:</b> when you report messages in a private chat, we copy the messages you selected into the report with your reason and any details, for our moderation team.</li>
      </ul>
      <h3>Automatically</h3>
      <ul>
        <li><b>Technical logs:</b> IP address, time, the page or API address requested, response codes, browser type. Login cookies, authorisation headers and query strings are not written to our access logs.</li>
        <li><b>Security records:</b> sign-in sessions (stored only as one-way hashes), rate-limit counters, safety-check results (for example, &ldquo;this post contained a risky command&rdquo;).</li>
        <li><b>AI usage records:</b> for each model call, the provider, model, number of tokens, cost and timing. These records do not contain your text.</li>
        <li><b>Private-chat records:</b> when each message was sent and by whom (stored with the chat, see above).</li>
        <li><b>Cookies:</b> only strictly necessary ones (keeping you signed in, protecting sign-in from forgery). No advertising or third-party tracking cookies.</li>
      </ul>
      <p>
        Please do not include personal data of yourself or others (names, phone numbers, addresses, ID numbers, health details,
        passwords, keys) in posts. Before a post with contact or ID details (email, phone, Aadhaar, PAN, card or bank numbers) is published, we show you what we found and ask you to confirm; keys and passwords are always blocked. These checks are not perfect and posts are public.
      </p>

      <h2>3. Why we use it</h2>
      <ul>
        <li>To provide the service: show your posts, run votes and notifications, keep you signed in.</li>
        <li>To run AI features you ask for: send the relevant question, answer and your instruction to the AI provider and return a draft for your approval. In private chats, the messages you tick are sent with your question and the answer is posted to the chat straight away.</li>
        <li>To deliver private chats: store and pass on encrypted messages and files to the chat&apos;s members, and keep your encrypted history backup.</li>
        <li>To handle reports and grievances about private chats, and act on them under these policies and the law.</li>
        <li><b>Safety and security:</b> detect leaked secrets, dangerous commands, spam, abuse, fraud and attacks; enforce our Terms.</li>
        <li><b>Quality and improvement:</b> we may review and analyse content, AI drafts, approvals and edits, and usage records to measure and improve answer quality, safety checks and the service. Where practical we use aggregated or de-identified data for this.</li>
        <li><b>Legal:</b> comply with Indian law, lawful orders and requests from authorities, and establish or defend legal claims.</li>
      </ul>
      <p>
        We do not use your private AI keys, sign-in sessions or private drafts to train AI models. We will not use your content to
        train third-party AI models without telling you first and giving you a choice.
      </p>

      <h2>4. Consent and legal basis</h2>
      <p>
        We process your personal data on the basis of the consent you give when you create an account (by accepting this policy
        and the Terms), and for the &ldquo;legitimate uses&rdquo; allowed by DPDP (for example, complying with law and court
        orders, and responding to emergencies). You can withdraw consent at any time by deleting your account (section 8);
        this does not affect processing already done, and some data is kept as explained in section 6.
      </p>

      <h2>5. Who we share it with</h2>
      <p>We share personal data only as needed to run the service, with these kinds of processors, under their terms:</p>
      <ul>
        <li><b>Hosting and storage:</b> Amazon Web Services (servers, database, file storage, key management), in the Mumbai (ap-south-1) region.</li>
        <li><b>Sign-in:</b> GitHub and Google, when you choose to sign in with them.</li>
        <li><b>Personal details in private conversations</b> (names, emails, phone numbers, ID numbers and similar) are replaced with placeholders before anything is sent to an AI provider, and put back only for the people in that conversation. Keys and passwords are removed and never sent.</li>
        <li><b>AI providers:</b> the platform AI provider we use (currently Groq) and, for &ldquo;Ask my AI&rdquo;, the provider you connected (for example OpenRouter and the model it routes to). They receive the text needed for your request and handle it under their own privacy policies and data terms, which may involve processing outside India.</li>
        <li><b>Domain and certificates:</b> our domain registrar and Let&apos;s Encrypt (no user content).</li>
        <li><b>AI answer quality:</b> LangChain (LangSmith, stored in its Asia-Pacific region) receives AI drafts for public questions — the question, your instruction and the draft — with personal details such as emails and phone numbers replaced by placeholders and secrets removed first, plus whether the draft was approved, edited (with the masked edited text) or discarded. No user ids or handles. From private clusters only if a cluster admin turned on &ldquo;Help improve Associator&apos;s AI&rdquo; (everyone in the cluster sees this): then the AI question and the AI&apos;s answer, masked the same way — other members&apos; messages and files are never sent. Never from one-to-one Messages. We use it to measure and improve answer quality and safety.</li>
        <li><b>Service monitoring:</b> Grafana Labs (Grafana Cloud, stored in India) receives technical measurements — request counts, timings, error types, the route pattern of each request (for example &ldquo;/drafts/&#123;id&#125;&rdquo;) and service logs. Before anything is sent we remove IP addresses, full links, query strings, cookies and authorisation headers; no posts, messages, prompts or files are sent.</li>
        <li><b>Authorities:</b> when required by Indian law or a valid order, for example under the IT Act and its rules.</li>
        <li><b>A successor:</b> if the service is transferred, under this policy or one at least as protective.</li>
      </ul>
      <p>Public content (your @handle, posts, votes counts) can be seen, copied and indexed by anyone, including search engines and AI crawlers. We cannot control copies made by others.</p>

      <h2>6. How long we keep it</h2>
      <ul>
        <li><b>Account and content:</b> while your account exists. When you delete a post or your account, it is removed from public view promptly.</li>
        <li><b>Removed content and related records:</b> kept for at least <b>180 days</b> after removal (or longer if an investigation or legal hold needs it), as the IT (Intermediary Guidelines) Rules, 2021 require.</li>
        <li><b>Logs:</b> kept for at least <b>180 days</b>, as directed by CERT-In, and then deleted or anonymised.</li>
        <li><b>Sign-in sessions:</b> up to 30 days; ended sessions are kept briefly for security.</li>
        <li><b>Private chats:</b> messages and files while the chat exists; they are deleted with the chat.</li>
        <li><b>Reports:</b> at least <b>180 days</b> after they are closed, or longer if an investigation or legal hold needs it.</li>
        <li><b>Backups:</b> may contain deleted data until the backup expires.</li>
        <li><b>Aggregated or de-identified data</b> that no longer identifies you may be kept for quality and statistics.</li>
      </ul>

      <h2>7. Security</h2>
      <p>
        We use reasonable security safeguards: encrypted connections (HTTPS), private networks for the database and backend,
        encryption at rest, one-way hashing of tokens and sign-in codes, encrypted AI keys, least-privilege access, and
        automated checks for leaked secrets, and encryption at rest for private chats with keys held in a cloud
        key-management service. Private chats are not end-to-end encrypted. No system is perfectly secure. If a personal data breach occurs, we will inform the
        Data Protection Board of India and affected users as DPDP requires.
      </p>

      <h2>8. Your rights</h2>
      <p>Under DPDP you can:</p>
      <ul>
        <li>ask for a summary of the personal data we hold about you and how we use it, and who we shared it with;</li>
        <li>ask us to correct, complete or update it;</li>
        <li>ask us to erase it (we will, except what the law requires us to keep, see section 6);</li>
        <li>withdraw consent (by deleting your account);</li>
        <li>nominate another person to exercise your rights if you die or become unable to;</li>
        <li>raise a grievance with us, and if not satisfied, complain to the Data Protection Board of India.</li>
      </ul>
      <p>To use these rights, email <b>{L.email}</b> from a way we can verify (for example, while signed in we may ask you to confirm). We reply within the time limits set by law.</p>

      <h2>9. Children</h2>
      <p>The service is only for people <b>18 or older</b>. We do not knowingly process children&apos;s data. If you believe a child has an account, contact us and we will delete it.</p>

      <h2>10. Data outside India</h2>
      <p>Our servers are in India (AWS Mumbai). Some processors (for example AI providers, GitHub, Google) may process data in other countries, as permitted by Indian law.</p>

      <h2>11. Changes</h2>
      <p>We may update this policy. We will change the version and date above and, for material changes, notify you on the site and ask for your consent again where the law requires.</p>

      <h2>12. Grievance Officer and contact</h2>
      <p>
        {L.grievanceOfficer}, Grievance Officer, {L.operator}, {L.address}. Email: <b>{L.email}</b>. We acknowledge complaints
        within 24 hours and resolve them within 15 days, or sooner where the law requires.
      </p>
      <p className="hint">This policy is provided for information and does not create rights beyond those given by law.</p>
    </LegalPage>
  );
}
