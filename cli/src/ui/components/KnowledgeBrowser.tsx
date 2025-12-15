/**
 * Knowledgebase Browser Component
 *
 * Interactive TUI for browsing DSL concepts, patterns, and API packs.
 */

import React, { useState, useEffect } from 'react'
import { Box, Text, useInput, useApp } from 'ink'

interface Concept {
  name: string
  description: string
  syntax?: string
  example?: string
}

interface Pattern {
  name: string
  description: string
  use_case: string
}

interface ApiPack {
  name: string
  provider: string
  category: string
  description: string
}

interface KnowledgeBrowserProps {
  concepts: Concept[]
  patterns: Pattern[]
  apiPacks: ApiPack[]
  initialTab?: 'concepts' | 'patterns' | 'api_packs'
}

type Tab = 'concepts' | 'patterns' | 'api_packs'

export function KnowledgeBrowser({
  concepts,
  patterns,
  apiPacks,
  initialTab,
}: KnowledgeBrowserProps) {
  const { exit } = useApp()
  const [activeTab, setActiveTab] = useState<Tab>(initialTab || 'concepts')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)

  // Get items for current tab
  const getItems = () => {
    switch (activeTab) {
      case 'concepts':
        return concepts
      case 'patterns':
        return patterns
      case 'api_packs':
        return apiPacks
    }
  }

  // Filter items by search
  const filteredItems = searchQuery
    ? getItems().filter((item) =>
        item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.description.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : getItems()

  const maxIndex = Math.max(0, filteredItems.length - 1)

  useInput((input, key) => {
    if (isSearching) {
      if (key.escape || key.return) {
        setIsSearching(false)
        return
      }
      if (key.backspace || key.delete) {
        setSearchQuery((q) => q.slice(0, -1))
        return
      }
      if (input && !key.ctrl && !key.meta) {
        setSearchQuery((q) => q + input)
        setSelectedIndex(0)
        return
      }
      return
    }

    if (input === 'q' || key.escape) {
      exit()
      return
    }

    if (input === '/') {
      setIsSearching(true)
      setSearchQuery('')
      return
    }

    if (key.tab || input === 'l') {
      const tabs: Tab[] = ['concepts', 'patterns', 'api_packs']
      const currentIdx = tabs.indexOf(activeTab)
      setActiveTab(tabs[(currentIdx + 1) % tabs.length])
      setSelectedIndex(0)
      return
    }

    if (input === 'h') {
      const tabs: Tab[] = ['concepts', 'patterns', 'api_packs']
      const currentIdx = tabs.indexOf(activeTab)
      setActiveTab(tabs[(currentIdx - 1 + tabs.length) % tabs.length])
      setSelectedIndex(0)
      return
    }

    if (key.upArrow || input === 'k') {
      setSelectedIndex((i) => Math.max(0, i - 1))
      return
    }

    if (key.downArrow || input === 'j') {
      setSelectedIndex((i) => Math.min(maxIndex, i + 1))
      return
    }
  })

  const selectedItem = filteredItems[selectedIndex]

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="cyan">
          {' '}DAZZLE Knowledgebase{' '}
        </Text>
        <Text dimColor> | </Text>
        <Text bold={activeTab === 'concepts'} color={activeTab === 'concepts' ? 'green' : undefined}>
          Concepts ({concepts.length})
        </Text>
        <Text dimColor> | </Text>
        <Text bold={activeTab === 'patterns'} color={activeTab === 'patterns' ? 'green' : undefined}>
          Patterns ({patterns.length})
        </Text>
        <Text dimColor> | </Text>
        <Text bold={activeTab === 'api_packs'} color={activeTab === 'api_packs' ? 'green' : undefined}>
          API Packs ({apiPacks.length})
        </Text>
      </Box>

      {/* Search bar */}
      {isSearching && (
        <Box marginBottom={1}>
          <Text color="yellow">Search: </Text>
          <Text>{searchQuery}</Text>
          <Text color="gray">_</Text>
        </Box>
      )}
      {!isSearching && searchQuery && (
        <Box marginBottom={1}>
          <Text dimColor>Filter: "{searchQuery}" ({filteredItems.length} results) - press / to search</Text>
        </Box>
      )}

      {/* Main content */}
      <Box flexDirection="row" height={18}>
        {/* List */}
        <Box flexDirection="column" width={30} borderStyle="single" borderColor="gray" paddingX={1}>
          {filteredItems.slice(0, 15).map((item, index) => (
            <Text
              key={item.name}
              color={index === selectedIndex ? 'cyan' : undefined}
              inverse={index === selectedIndex}
            >
              {index === selectedIndex ? '> ' : '  '}
              {item.name}
            </Text>
          ))}
          {filteredItems.length === 0 && (
            <Text dimColor italic>
              No {activeTab.replace('_', ' ')} found
            </Text>
          )}
          {filteredItems.length > 15 && (
            <Text dimColor>... and {filteredItems.length - 15} more</Text>
          )}
        </Box>

        {/* Detail panel */}
        <Box
          flexDirection="column"
          flexGrow={1}
          borderStyle="single"
          borderColor="gray"
          paddingX={1}
          marginLeft={1}
        >
          {selectedItem && activeTab === 'concepts' && (
            <ConceptDetail concept={selectedItem as Concept} />
          )}
          {selectedItem && activeTab === 'patterns' && (
            <PatternDetail pattern={selectedItem as Pattern} />
          )}
          {selectedItem && activeTab === 'api_packs' && (
            <ApiPackDetail pack={selectedItem as ApiPack} />
          )}
          {!selectedItem && (
            <Text dimColor>Select an item to view details</Text>
          )}
        </Box>
      </Box>

      {/* Footer */}
      <Box marginTop={1}>
        <Text dimColor>
          ↑↓/jk Navigate | Tab/hl Switch | / Search | q Quit
        </Text>
      </Box>
    </Box>
  )
}

function ConceptDetail({ concept }: { concept: Concept }) {
  return (
    <Box flexDirection="column">
      <Text bold color="yellow">
        {concept.name}
      </Text>
      <Text> </Text>
      <Text wrap="wrap">{concept.description}</Text>
      {concept.syntax && (
        <>
          <Text> </Text>
          <Text bold>Syntax:</Text>
          <Text color="cyan">{concept.syntax}</Text>
        </>
      )}
      {concept.example && (
        <>
          <Text> </Text>
          <Text bold>Example:</Text>
          <Box borderStyle="round" borderColor="gray" paddingX={1}>
            <Text>{concept.example}</Text>
          </Box>
        </>
      )}
    </Box>
  )
}

function PatternDetail({ pattern }: { pattern: Pattern }) {
  return (
    <Box flexDirection="column">
      <Text bold color="yellow">
        {pattern.name}
      </Text>
      <Text> </Text>
      <Text wrap="wrap">{pattern.description}</Text>
      <Text> </Text>
      <Text bold>Use Case:</Text>
      <Text wrap="wrap" color="gray">{pattern.use_case}</Text>
    </Box>
  )
}

function ApiPackDetail({ pack }: { pack: ApiPack }) {
  return (
    <Box flexDirection="column">
      <Text bold color="yellow">
        {pack.name}
      </Text>
      <Text> </Text>
      <Text>
        <Text bold>Provider: </Text>
        <Text color="cyan">{pack.provider}</Text>
      </Text>
      <Text>
        <Text bold>Category: </Text>
        <Text>{pack.category}</Text>
      </Text>
      <Text> </Text>
      <Text wrap="wrap">{pack.description}</Text>
    </Box>
  )
}

export default KnowledgeBrowser
