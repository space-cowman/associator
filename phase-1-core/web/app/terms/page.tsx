import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/Legal";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = { title: `Terms of Service · ${LEGAL.service}` };

const L = LEGAL;

/** The Terms of Service. */
export default function Terms() {
  return (
    <LegalPage title="Terms of Service">
      <p>
        These Terms are an agreement between you and {L.operator} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) for using {L.service} at
        {" "}{L.site}, its API and its connectors (the &ldquo;Service&rdquo;). By creating an account or using the Service you
        agree to these Terms and the <Link href="/privacy">Privacy Policy</Link>. If you do not agree, do not use the Service.
        These Terms are an electronic record under the Information Technology Act, 2000 and do not need a signature.
      </p>

      <h2>1. Who can use it</h2>
      <p>You must be at least <b>18 years old</b> and able to enter a binding contract under Indian law. You are responsible for everything done through your account and your access tokens. Keep them safe.</p>

      <h2>2. What the Service is</h2>
      <p>
        A public question-and-answer community. People answer themselves or draft answers with their own AI or the platform AI;
        every AI draft must be approved by a person before it is posted. The Service is a <b>beta</b>: features may change,
        break or stop, and data loss is possible. We may change, suspend or end any part of it at any time.
      </p>

      <h2>3. Your content</h2>
      <ul>
        <li>You keep ownership of what you post. You give us a worldwide, non-exclusive, royalty-free licence to host, store, copy, display, adapt (for example format or resize) and distribute it to run, promote and improve the Service. This licence continues for content already shared or copied by others, and for copies we must keep by law.</li>
        <li>Posts are <b>public</b>. Others may read, quote and reuse them. Do not post anything you want to keep private.</li>
        <li>You confirm you have the right to post your content and that it does not break the law or anyone&apos;s rights.</li>
        <li>When you approve an AI draft, it becomes your post and your responsibility, exactly as if you wrote it.</li>
      </ul>

      <h2>4. What you must not post or do</h2>
      <p>As required by the IT (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021, you must not host, display, upload, modify, publish, transmit, store, update or share anything that:</p>
      <ul>
        <li>belongs to someone else and you have no right to;</li>
        <li>is obscene, pornographic, paedophilic, invasive of another&apos;s privacy (including bodily privacy), insulting or harassing on the basis of gender, racially or ethnically objectionable, relating to or encouraging money laundering or gambling, or promoting enmity between groups on the grounds of religion or caste with intent to incite violence;</li>
        <li>is harmful to children;</li>
        <li>infringes any patent, trademark, copyright or other proprietary right;</li>
        <li>deceives or misleads about its origin, or knowingly communicates misinformation or information that is patently false and untrue or misleading;</li>
        <li>impersonates another person;</li>
        <li>threatens the unity, integrity, defence, security or sovereignty of India, friendly relations with foreign States, or public order, or incites any offence, or prevents investigation of any offence, or insults another nation;</li>
        <li>contains software viruses or any code designed to interrupt, destroy or limit the functionality of any computer resource;</li>
        <li>violates any law in force.</li>
      </ul>
      <p>
        You also must not: post other people&apos;s personal data, passwords or keys; try to break, overload, scrape at scale or
        bypass security or rate limits; use the Service or AI features to create spam or malware; misrepresent AI-written text
        as checked when you have not read it; or use the Service to build a competing dataset without our permission.
      </p>

      <h2>5. Moderation and enforcement</h2>
      <p>
        We may (but are not obliged to) review, label, hide or remove content, and suspend or close accounts, that we believe break
        these Terms or the law, with or without notice. We act on valid court orders and government notices within the times the law
        sets. Repeated or serious violations lead to account termination. Removed content and related records are kept as described
        in the Privacy Policy.
      </p>

      <h2>6. AI features</h2>
      <ul>
        <li>AI output can be <b>wrong, incomplete, outdated, biased or unsafe</b>. It is not professional advice (legal, medical, financial, security or otherwise). Check it before relying on it, especially commands and code.</li>
        <li>When you connect your own AI provider, you are responsible for your account, keys, costs and compliance with that provider&apos;s terms. We only make the calls you ask for.</li>
        <li>Requests are sent to third-party AI providers who process them under their own terms. We may change providers or models at any time.</li>
        <li>Safety labels (for example &ldquo;risky command&rdquo;) are automated hints, not guarantees.</li>
      </ul>

      <h2>6A. Private clusters and Messages</h2>
      <ul>
        <li>Private chats are visible only to their members and are stored on our servers, encrypted at rest. They are <b>not end-to-end encrypted</b> (see the Privacy Policy). These Terms (section 4) apply in private chats too.</li>
        <li>Members can <b>report</b> messages. We review reported messages and may act under section 5 (for example, remove someone or close an account).</li>
        <li>In a private chat, an AI&apos;s answer is <b>posted straight away</b>, without the approval step used in public clusters. You are responsible for what you ask it and which messages you share with it. Admins can switch AI off for a cluster.</li>
        <li>Invitations and messages from people you have not chatted with arrive as requests you can accept, ignore or block.</li>
        <li>A cluster admin can turn on <b>&ldquo;Help improve Associator&apos;s AI&rdquo;</b>. While it is on (shown to everyone in the cluster), the question you ask an AI there and the AI&apos;s answer are sent, with names and personal details hidden, to our AI-quality service (see the Privacy Policy). Other members&apos; messages and files are never sent.</li>
      </ul>

      <h2>7. Our rights</h2>
      <p>The Service, its software, design and brand belong to us or our licensors. You get a limited, revocable, non-transferable right to use it under these Terms. Feedback you give us may be used freely without obligation to you.</p>

      <h2>8. Disclaimers</h2>
      <p>
        The Service and all content (including user posts and AI output) are provided <b>&ldquo;as is&rdquo; and &ldquo;as
        available&rdquo;</b>, without warranties of any kind, express or implied, including fitness for a particular purpose,
        accuracy, availability or non-infringement, to the fullest extent permitted by law. Content is posted by users; we do not
        endorse it and are not responsible for it, as an intermediary under section 79 of the IT Act.
      </p>

      <h2>9. Limitation of liability</h2>
      <p>
        To the fullest extent permitted by law, we are not liable for any indirect, incidental, special, consequential or
        punitive damages, or for loss of profits, data, goodwill or business, arising from your use of the Service, content on
        it, or AI output, even if told they were possible. Our total liability for any claim relating to the Service is limited
        to the amount you paid us for the Service in the 12 months before the claim, or INR 1,000 if you paid nothing. Nothing in
        these Terms limits liability that cannot be limited under Indian law.
      </p>

      <h2>10. Indemnity</h2>
      <p>You agree to indemnify and hold harmless {L.operator} from claims, losses and costs (including reasonable legal fees) arising from your content, your use of the Service, AI drafts you approve, or your breach of these Terms or the law.</p>

      <h2>11. Ending your account</h2>
      <p>You may stop using the Service and ask us to delete your account at any time (see the Privacy Policy). We may suspend or end your access as described in section 5. Sections that by their nature should survive (content licence for copies already made, disclaimers, liability, indemnity, law) survive termination.</p>

      <h2>12. Changes to these Terms</h2>
      <p>We may update these Terms. The version and date above will change; for material changes we will notify you on the Service and may ask you to accept again. Continuing to use the Service after changes take effect means you accept them.</p>

      <h2>13. Law and disputes</h2>
      <p>These Terms are governed by the laws of India. Courts at {L.courts}, India have exclusive jurisdiction, subject to any rights you have under consumer protection law. Before going to court, please contact us so we can try to resolve the issue.</p>

      <h2>14. Grievances and contact</h2>
      <p>
        Grievance Officer: {L.grievanceOfficer}, {L.operator}, {L.address}. Email: <b>{L.email}</b>. Complaints about content
        or these Terms are acknowledged within 24 hours and resolved within 15 days (content that exposes someone&apos;s private
        area or is sexual in nature, or impersonates someone, is acted on within 24 hours of a complaint).
      </p>
      <p>If any part of these Terms is unenforceable, the rest stays in force. Not enforcing a right is not a waiver. These Terms and the Privacy Policy are the whole agreement between us about the Service.</p>
    </LegalPage>
  );
}
