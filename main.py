import pymupdf
import json
import re

def is_sub_question(line):
    # Matches patterns like "(a)", "a)", "(1)", etc.
    return bool(re.match(r'^\(?[a-zA-Z0-9]+\)?[:\s]', line))

def is_new_question(line):
    return bool(re.match(r'^Problem\s+\d+', line))

def is_latex(line):
    # Detect LaTeX by checking for backslashes and common LaTeX symbols
    return bool(re.search(r'\\[a-zA-Z]+|[_^{}]|\\', line))

# Mapping of special characters and Unicode symbols to LaTeX equivalents
special_characters = {
    'θ': '\\theta',
    '×': '\\times',
    '−': '-',    # Minus sign
    '–': '-',    # En dash
    '—': '-',    # Em dash
    '→': '\\to',
    '√': '\\sqrt',
    '²': '^2',
    '³': '^3',
    'α': '\\alpha',
    'β': '\\beta',
    'γ': '\\gamma',
    'μ': '\\mu',
    'σ': '\\sigma',
    'Δ': '\\Delta',
    '∑': '\\sum',
    '∫': '\\int',
    '∞': '\\infty',
    '_': '\\_',
    # Add any other necessary mappings
}

def replace_special_characters(line):
    for char, latex_char in special_characters.items():
        line = line.replace(char, latex_char)
    return line

def fix_hyphenated_words(lines):
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.endswith('-') and i+1 < len(lines):
            next_line = lines[i+1]
            # Merge only if it's a continuation (next line starts with lowercase letter)
            if next_line and next_line[0].islower():
                merged_line = line[:-1] + next_line
                fixed_lines.append(merged_line)
                i += 2
                continue
        fixed_lines.append(line)
        i += 1
    return fixed_lines

def is_header_or_footer(line, headers_and_footers):
    return line in headers_and_footers

def extract_text_from_pdf(path):
    doc = pymupdf.open(path)
    questions = []
    question_number = 0
    question = {"number": str(question_number), "body": {"parts": [], "children": []}}
    current_child = None

    # Collect possible headers and footers
    header_footer_candidates = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if lines:
            # Assuming headers and footers are the first and last lines
            header_footer_candidates.append(lines[0])
            header_footer_candidates.append(lines[-1])

    # Determine common headers and footers
    header_footer_counts = {}
    for line in header_footer_candidates:
        header_footer_counts[line] = header_footer_counts.get(line, 0) + 1

    threshold = len(doc) // 2  # Appear on more than half the pages
    common_headers_and_footers = {line for line, count in header_footer_counts.items() if count > threshold}

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        lines = fix_hyphenated_words(lines)
        # Skip any lines before the first question
        for line in lines:
            if "Problem" in line:
                lines = lines[lines.index(line):]
                break

        i = 0
        while i < len(lines):
            line = lines[i]
            # Skip common headers and footers
            if is_header_or_footer(line, common_headers_and_footers):
                i += 1
                continue
            # Detect new question
            if is_new_question(line):
                if question["body"]["parts"] or question["body"]["children"]:
                    questions.append(question)
                    question_number += 1
                question = {"number": str(question_number), "body": {"parts": [], "children": []}}
                current_child = None
                i += 1
                continue

            # Process initial text before sub-questions
            if not question["body"]["children"]:
                # Split line if it contains a URL or periods
                if 'http' in line or '.' in line:
                    temp_parts = re.split(r'(\s*https?://\S+|\.\s*)', line)
                    for part in temp_parts:
                        if part.strip():
                            if 'http' in part:
                                question["body"]["parts"].append({"type": "text", "body": part.strip()})
                            elif part.strip() == '.':
                                question["body"]["parts"].append({"type": "text", "body": part.strip()})
                            else:
                                # Further split if there are multiple sentences
                                sentences = re.split(r'(\.\s*)', part)
                                for sentence in sentences:
                                    if sentence.strip():
                                        question["body"]["parts"].append({"type": "text", "body": sentence.strip()})
                    i += 1
                    continue

            # Detect sub-question
            if is_sub_question(line):
                if current_child:
                    question["body"]["children"].append(current_child)
                current_child = {"parts": []}

                # Start accumulating sub-question content
                sub_question_content = line
                i += 1
                # Continue accumulating lines until the next sub-question or new question is detected
                while i < len(lines) and not is_sub_question(lines[i]) and not is_new_question(lines[i]):
                    sub_question_content += ' ' + lines[i]
                    i += 1

                # Process sub-question content
                match = re.match(r'^(\(?[a-zA-Z0-9]+\)?[:\s])(.*)', sub_question_content)
                if match:
                    identifier = match.group(1).strip()
                    rest_of_line = match.group(2).strip()

                    current_child["parts"].append({"type": "text", "body": identifier})

                    if rest_of_line:
                        rest_of_line = replace_special_characters(rest_of_line)
                        # Add \text{} around function names
                        rest_of_line = re.sub(r'^(\w+)', r'\\text{\1}', rest_of_line)
                        if is_latex(rest_of_line):
                            part = {"type": "LaTeX", "body": rest_of_line}
                        else:
                            part = {"type": "text", "body": rest_of_line}
                        current_child["parts"].append(part)
                else:
                    # If no match, treat the whole content as text
                    sub_question_content = replace_special_characters(sub_question_content)
                    current_child["parts"].append({"type": "text", "body": sub_question_content})
                continue  # Skip incrementing i here since we've already done it in the loop

            # Process the line
            line = replace_special_characters(line)
            if is_latex(line):
                part = {"type": "LaTeX", "body": line}
            else:
                # Handle URLs and split lines if necessary
                if 'http' in line or '.' in line:
                    temp_parts = re.split(r'(\s*https?://\S+|\.\s*)', line)
                    for part_text in temp_parts:
                        if part_text.strip():
                            question["body"]["parts"].append({"type": "text", "body": part_text.strip()})
                    i += 1
                    continue
                else:
                    part = {"type": "text", "body": line}

            if current_child:
                current_child["parts"].append(part)
            else:
                question["body"]["parts"].append(part)

            i += 1  # Move to the next line

        # After processing all lines on the page
        if current_child:
            question["body"]["children"].append(current_child)
            current_child = None

    # Add the last question
    if question["body"]["parts"] or question["body"]["children"]:
        questions.append(question)

    return questions

def main():
    pdf_path = "mit18_s096iap23_pset1.pdf"  # Replace with your PDF file path
    extracted_questions = extract_text_from_pdf(pdf_path)
    output_json_path = "output.json"  # Output JSON file path
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(extracted_questions, f, indent=2, ensure_ascii=False)
    print(f"Extraction complete! JSON saved to {output_json_path}")

if __name__ == "__main__":
    main()
