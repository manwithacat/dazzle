/**
 * DSL Explorer Component
 *
 * Interactive TUI for exploring DAZZLE project structure.
 */

import React, { useState, useEffect } from 'react'
import { Box, Text, useInput, useApp } from 'ink'

interface Entity {
  name: string
  label: string
  fields: { name: string; type: string; required: boolean }[]
}

interface Surface {
  name: string
  label: string
  entity: string
  mode: string
}

interface ExplorerProps {
  entities: Entity[]
  surfaces: Surface[]
  initialTab?: 'entities' | 'surfaces'
  onExit?: () => void
}

type Tab = 'entities' | 'surfaces'

export function Explorer({ entities, surfaces, initialTab, onExit }: ExplorerProps) {
  const { exit } = useApp()
  const [activeTab, setActiveTab] = useState<Tab>(initialTab || 'entities')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [showDetail, setShowDetail] = useState(false)

  const items = activeTab === 'entities' ? entities : surfaces
  const maxIndex = items.length - 1

  useInput((input, key) => {
    if (input === 'q' || key.escape) {
      onExit?.()
      exit()
      return
    }

    if (key.tab) {
      setActiveTab((t) => (t === 'entities' ? 'surfaces' : 'entities'))
      setSelectedIndex(0)
      setShowDetail(false)
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

    if (key.return || input === ' ') {
      setShowDetail((d) => !d)
      return
    }
  })

  const selectedItem = items[selectedIndex]

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="cyan">
          {' '}DAZZLE Explorer{' '}
        </Text>
        <Text dimColor> | </Text>
        <Text bold={activeTab === 'entities'} color={activeTab === 'entities' ? 'green' : undefined}>
          Entities ({entities.length})
        </Text>
        <Text dimColor> | </Text>
        <Text bold={activeTab === 'surfaces'} color={activeTab === 'surfaces' ? 'green' : undefined}>
          Surfaces ({surfaces.length})
        </Text>
      </Box>

      {/* Main content */}
      <Box flexDirection="row" height={15}>
        {/* List */}
        <Box flexDirection="column" width={30} borderStyle="single" borderColor="gray" paddingX={1}>
          {items.map((item, index) => (
            <Text
              key={item.name}
              color={index === selectedIndex ? 'cyan' : undefined}
              inverse={index === selectedIndex}
            >
              {index === selectedIndex ? '▸ ' : '  '}
              {item.name}
            </Text>
          ))}
          {items.length === 0 && (
            <Text dimColor italic>
              No {activeTab} found
            </Text>
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
          {selectedItem && activeTab === 'entities' && (
            <EntityDetail entity={selectedItem as Entity} />
          )}
          {selectedItem && activeTab === 'surfaces' && (
            <SurfaceDetail surface={selectedItem as Surface} />
          )}
          {!selectedItem && (
            <Text dimColor>Select an item to view details</Text>
          )}
        </Box>
      </Box>

      {/* Footer */}
      <Box marginTop={1}>
        <Text dimColor>
          ↑↓ Navigate | Tab Switch | Enter Details | q Quit
        </Text>
      </Box>
    </Box>
  )
}

function EntityDetail({ entity }: { entity: Entity }) {
  return (
    <Box flexDirection="column">
      <Text bold color="yellow">
        entity {entity.name}
      </Text>
      <Text color="gray">"{entity.label}"</Text>
      <Text> </Text>
      <Text bold>Fields:</Text>
      {entity.fields.slice(0, 10).map((field) => (
        <Text key={field.name}>
          <Text color="cyan">{field.name}</Text>
          <Text dimColor>: </Text>
          <Text>{field.type}</Text>
          {field.required && <Text color="red"> *</Text>}
        </Text>
      ))}
      {entity.fields.length > 10 && (
        <Text dimColor>... and {entity.fields.length - 10} more</Text>
      )}
    </Box>
  )
}

function SurfaceDetail({ surface }: { surface: Surface }) {
  return (
    <Box flexDirection="column">
      <Text bold color="yellow">
        surface {surface.name}
      </Text>
      <Text color="gray">"{surface.label}"</Text>
      <Text> </Text>
      <Text>
        <Text bold>Entity: </Text>
        <Text color="cyan">{surface.entity}</Text>
      </Text>
      <Text>
        <Text bold>Mode: </Text>
        <Text>{surface.mode}</Text>
      </Text>
    </Box>
  )
}

export default Explorer
